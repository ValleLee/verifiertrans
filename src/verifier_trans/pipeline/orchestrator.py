#!/usr/bin/env python3
"""Deterministic controller for the functional-verifier pipeline.

PREPARE -> SINGLE CONVERTER -> SEMANTIC/CORE GATES -> QA -> REPAIR -> PACKAGE

Agents create repository artifacts. Scripts execute them. Judges classify
candidate semantics. The controller routes only structured evidence.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import shutil
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from ..agents.judge import judge, write_judgement
from ..agents.miniswe_session import run_miniswe_session
from ..deterministic.validation.artifact_contract import add_contract
from ..deterministic.execution import EXECUTION_CONTRACT_VERSION
from ..deterministic.validation.normalize_manifest import normalize_manifest
from ..deterministic.validation.positive_structure import structural_precheck
from ..deterministic.reporting.report import write_report
from ..paths import (
    DEFAULT_CONFIG,
    DEFAULT_ENV,
    DEFAULT_RUNS_ROOT,
    PROJECT_ROOT,
    RunLayout,
    attempt_from_path,
)
from .artifacts import (
    copy_tree,
    file_digest,
    load_optional_json,
    publish_final_task,
    save_json,
)
from .converter import self_review_passed, session_step_cap, terminal_submission
from .qa import (
    POSITIVE_CONTRACT_VERSION,
    candidate_files,
    candidate_infra_failure,
    negative_execution_contract,
    load_evidence,
    positive_candidate_contract,
    positive_execution_contract,
    save_evidence,
    validated_positive_contract,
)
from .state import append_event, infra_failure, utc


def load_config(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"invalid config: {path}")
    return value


def prompt_path(config: dict[str, Any], name: str) -> Path:
    """Resolve a repository-relative prompt path from experiment config."""
    relative = str((config.get("prompts") or {}).get(name) or "")
    if not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError(f"invalid relative prompt path for {name}: {relative!r}")
    path = (PROJECT_ROOT / relative).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"configured prompt does not exist for {name}: {path}")
    return path


def load_credentials(path: Path) -> dict[str, dict[str, str]]:
    known = {"converter", "solver", "verifier_judge", "solution_judge", "mutation_judge", "default"}
    profiles: dict[str, dict[str, str]] = {name: {} for name in known}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise ValueError(f"expected KEY=VALUE, got {line!r}")
        key, value = line.split("=", 1)
        key, value = key.strip().lower(), value.strip().strip('"').strip("'")
        target, field = "default", key
        if "_" in key:
            prefix, candidate = key.split("_", 1)
            if prefix in known and candidate:
                target, field = prefix, candidate
        profiles[target][field] = value
    for role in known - {"default"}:
        merged = dict(profiles["default"])
        merged.update(profiles[role])
        profiles[role] = merged
    required = {"base_url", "model", "api_key"}
    for role, profile in profiles.items():
        if required - profile.keys():
            raise ValueError(f"credentials file lacks {', '.join(sorted(required - profile.keys()))} for {role}")
    return profiles


def role_credentials(credentials: dict[str, dict[str, str]], role: str) -> dict[str, str]:
    value = dict(credentials["default"])
    value.update(credentials.get(role, {}))
    return value


def run_script(command: list[str]) -> tuple[int, str]:
    result = subprocess.run(command, cwd=PROJECT_ROOT, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    print(result.stdout, end="")
    return result.returncode, result.stdout


def reset_output(path: Path) -> None:
    # Classified attempts expose several writable outputs through relative
    # compatibility symlinks (for example .compat/verifier -> converter/current).
    # Clear the resolved target while preserving the logical link; rmtree on
    # the symlink itself raises ``OSError: Cannot call rmtree on a symbolic
    # link`` and aborts an otherwise recoverable Converter repair.
    if path.is_symlink():
        resolved = path.resolve(strict=False)
        if resolved.is_dir():
            path = resolved
        else:
            path.unlink()
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


@contextmanager
def controller_session_lock(workspace: Path):
    """Serialize all controller work for one prepared attempt.

    The Converter lock alone is insufficient: a second resume can otherwise
    run QA or overwrite report/state while the first controller is still
    committing a revision.  The lock is advisory through the process lifetime
    and is released automatically if the controller exits.
    """
    lock_path = workspace / "run" / "controller_session.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    stream = lock_path.open("a+", encoding="utf-8")
    try:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("another controller session is active for this attempt") from exc
        yield
    finally:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        finally:
            stream.close()


@contextmanager
def converter_session_lock(workspace: Path):
    """Prevent concurrent Converter sessions from sharing a live revision.

    Converter sessions write many files over several minutes.  A second
    controller must not validate or commit while the first one is still
    finishing, and a late session must never replace the verifier selected by
    the current revision loop.
    """
    lock_path = workspace / "run" / "converter_session.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    stream = lock_path.open("a+", encoding="utf-8")
    try:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("another Converter session is active for this workspace") from exc
        yield
    finally:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        finally:
            stream.close()


def run_converter(workspace: Path, config: dict[str, Any], credentials: dict[str, dict[str, str]],
                  revision: int, repair_packet: dict[str, Any] | None) -> str:
    if repair_packet:
        task = (
            "Repair the current verifier revision using the following executable evidence. "
            "Preserve every already-valid F2P mapping and do not broaden the specification. "
            "All commands and paths must be relative to the role workspace: use app/ for the "
            "repository, output/ for the formal artifact, scratch/ for experiments, and public/, restricted/, reference/ "
            "or run/ for evidence. Never put a host absolute path in a shell command.\n\n"
            + json.dumps(repair_packet, ensure_ascii=False, indent=2)
        )
    else:
        task = (
            "Build the first functional verifier revision. The complete repository and all source "
            "evidence are available, but explore them progressively as each F2P intent requires; "
            "do not treat Gold-touched files as a whitelist and do not default to a full-repository "
            "scan. Read public/problem_statement.md, "
            "public/interface_contract.md, restricted/original_tests, restricted/test_seeds.json, "
            "restricted/resolved_test_selectors.json and the repository. Use sealed evidence only "
            "as construction evidence. Convert every historical F2P, retain exact P2P regression "
            "coverage, produce a structured conversion trace for every F2P, keep output/ limited to "
            "the final tests, small fixtures and audit files (never copy dependencies, archives or "
            "scratch experiments there), use scratch/ for disposable work, do not fetch/install packages or use registry commands, "
            "write the final instruction scope and self-review, "
            "then submit."
        )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    trajectory = workspace / "artifacts" / "trajectories" / f"converter_rev_{revision}_{stamp}.json"
    staging = workspace / "artifacts" / "staging" / f"converter_rev_{revision}_{stamp}"
    with converter_session_lock(workspace):
        result = run_miniswe_session(
            project_root=PROJECT_ROOT, workspace=workspace, role="converter",
            prompt_path=prompt_path(config, "converter"),
            credentials=role_credentials(credentials, "converter"), config=config, task=task,
            converter_output_dir=staging,
            trajectory_path=trajectory,
            step_limit=session_step_cap(config, "converter", repair=bool(repair_packet)),
        )
        (workspace / "artifacts" / "trajectories" / f"converter_rev_{revision}_{stamp}.final.txt").write_text(result + "\n", encoding="utf-8")
        if not terminal_submission(result):
            raise RuntimeError("converter did not emit the explicit submission signal")
        # Commit only the successfully submitted, session-isolated payload.
        copy_tree(staging, workspace / "verifier")
    return result


def snapshot_verifier(workspace: Path, revision: int) -> None:
    target = workspace / "artifacts" / "verifier" / f"rev_{revision:03d}"
    if target.exists():
        raise RuntimeError(f"refusing to overwrite immutable verifier revision: {target}")
    copy_tree(workspace / "verifier", target)
    manifest_path = workspace / "verifier" / "manifest.json"
    save_json(workspace / "artifacts" / "verifier" / f"rev_{revision:03d}.json", {
        "schema_version": "3.0", "revision": revision,
        "verifier_hash": file_digest(workspace / "verifier"),
        "manifest": json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {},
    })


def run_hard_validator(workspace: Path, config: dict[str, Any], revision: int) -> dict[str, Any]:
    """Run the one authoritative deterministic Base/Gold/P2P hard gate."""
    rc, _ = run_script([
        sys.executable, "-m", "verifier_trans.deterministic.replay.verifier", str(workspace),
        "--timeout", str(config["experiment"].get("verifier_timeout_seconds", 1800)),
        "--round", str(revision), "--repeat", str(config["experiment"].get("replay_repeats", 2)),
    ])
    path = workspace / "run" / "check.json"
    check = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {
        "accepted": False, "failure_domain": "infrastructure", "reason_code": f"missing_check_rc_{rc}"
    }
    check["execution_contract"] = EXECUTION_CONTRACT_VERSION
    save_json(workspace / "artifacts" / "core_gate" / f"rev_{revision:03d}.json", check)
    return check


def run_sanity(workspace: Path, revision: int) -> dict[str, Any]:
    rc, _ = run_script([
        sys.executable, "-m", "verifier_trans.deterministic.validation.validate_verifier",
        str(workspace), "--revision", str(revision),
    ])
    path = workspace / "artifacts/validation" / f"sanity_rev_{revision:03d}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {
        "status": "REPAIR", "errors": [f"missing_sanity_rc_{rc}"]
    }


def normalize_manifest_artifact(workspace: Path, revision: int) -> dict[str, Any]:
    """Migrate only known legacy manifest shapes, without a model revision."""
    result = normalize_manifest(workspace)
    result["revision"] = revision
    save_json(workspace / "artifacts/validation" / f"manifest_normalization_rev_{revision:03d}.json", result)
    if result.get("changed"):
        append_event(workspace, "ARTIFACT_NORMALIZED", f"manifest_rev_{revision}", **result)
    return result


# Compatibility for callers that imported the old name. The pipeline itself
# uses run_hard_validator so Core Gate remains only the report/state label.
run_core = run_hard_validator


def verifier_tree(path: Path, limit: int = 220_000) -> dict[str, str]:
    result: dict[str, str] = {}
    used = 0
    for item in sorted(path.rglob("*")):
        if not item.is_file():
            continue
        content = item.read_text(encoding="utf-8", errors="replace")
        result[str(item.relative_to(path))] = content[: max(0, limit - used)]
        used += len(content)
        if used >= limit:
            break
    return result


def semantic_verifier_tree(path: Path) -> dict[str, str]:
    """Return the semantic judge view without replay-scale P2P payloads.

    Exact P2P accounting is checked deterministically by sanity and replay.
    Sending hundreds of selector ids and the duplicated manifest list to the
    semantic model wastes context and materially increases API latency.
    """
    result: dict[str, str] = {}
    for item in sorted(path.rglob("*")):
        if not item.is_file() or item.name == "p2p_nodes.txt":
            continue
        if item.name == "manifest.json":
            try:
                manifest = json.loads(item.read_text(encoding="utf-8"))
                p2p = manifest.pop("source_p2p_coverage", [])
                manifest["source_p2p_coverage_summary"] = {
                    "count": len(p2p) if isinstance(p2p, list) else None,
                    "present": bool(p2p),
                }
                result[str(item.relative_to(path))] = json.dumps(
                    manifest, ensure_ascii=False, indent=2
                )
                continue
            except (OSError, json.JSONDecodeError):
                pass
        result[str(item.relative_to(path))] = item.read_text(
            encoding="utf-8", errors="replace"
        )
    return result


def run_verifier_judge(workspace: Path, config: dict[str, Any],
                       credentials: dict[str, dict[str, str]], revision: int) -> dict[str, Any]:
    seeds = json.loads((workspace / "restricted/test_seeds.json").read_text(encoding="utf-8"))
    selectors = json.loads(
        (workspace / "restricted/resolved_test_selectors.json").read_text(encoding="utf-8")
    )
    evidence = {
        "revision": revision,
        "problem_statement": (workspace / "public/problem_statement.md").read_text(encoding="utf-8"),
        "interface_contract": (workspace / "public/interface_contract.md").read_text(encoding="utf-8"),
        # Semantic Judge reviews the conversion scope. Do not spend its output
        # budget on the complete inherited P2P list; the manifest and
        # conversion log still expose P2P separation and its count.
        "historical_f2p": {
            "fail_to_pass_source": seeds.get("fail_to_pass_source", []),
            # The source ids identify the dataset's historical nodes; the
            # resolved ids are the executable canonical contract used by
            # sanity/replay.  Supplying both prevents the semantic judge from
            # treating a valid source-to-resolved normalization as lost
            # accounting.
            "fail_to_pass_resolved": (selectors.get("fail_to_pass") or {}).get("resolved", []),
            "pass_to_pass_count": len(seeds.get("pass_to_pass_source", [])),
        },
        "verifier": semantic_verifier_tree(workspace / "verifier"),
        "sanity": json.loads((workspace / "artifacts/validation" / f"sanity_rev_{revision:03d}.json").read_text(encoding="utf-8")),
    }
    result = judge(config=config, credentials=credentials, role="verifier_judge",
                   system=prompt_path(config, "semantic_judge").read_text(encoding="utf-8"),
                   evidence=evidence)
    result = add_contract(
        workspace, revision, result,
        status="PASS" if str(result.get("verdict", "")).upper() == "PASS" else "FAIL",
        failure_class=("NONE" if str(result.get("verdict", "")).upper() == "PASS"
                       else "VERIFIER_SEMANTIC"),
    )
    write_judgement(workspace / "artifacts/semantic_reviews" / f"rev_{revision:03d}.json", result)
    return result


def reusable_revision_evidence(
    workspace: Path, path: Path, revision: int, *, kind: str,
) -> dict[str, Any] | None:
    """Return immutable PASS evidence only when it still describes this verifier.

    A resumed run may continue at QA after a controller interruption.  Reusing
    evidence is safe only when both the revision and the complete verifier
    digest match; otherwise the current revision must go through its gates
    again.
    """
    value = load_optional_json(path)
    if not isinstance(value, dict):
        return None
    if value.get("verifier_revision") != revision:
        return None
    if value.get("verifier_hash") != file_digest(workspace / "verifier"):
        return None
    if str(value.get("status", "")).upper() != "PASS":
        return None
    if kind == "semantic" and str(value.get("verdict", "")).upper() != "PASS":
        return None
    if kind == "hard" and value.get("accepted") is not True:
        return None
    if kind == "hard" and value.get("execution_contract") != EXECUTION_CONTRACT_VERSION:
        return None
    return value


def phase_summary(workspace: Path, final: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    """Expose stage-level outcomes without requiring consumers to parse events."""
    revision = final.get("revision")
    return {
        "prepare": {
            "source_preflight": load_optional_json(workspace / "run/source_preflight.json"),
            "environment_preflight": load_optional_json(workspace / "run/environment_preflight.json"),
        },
        "converter": {
            "revision": revision,
            "verifier_snapshot": str(workspace / "artifacts/verifier" / f"rev_{int(revision):03d}")
            if isinstance(revision, int) else None,
        },
        "semantic_judge": load_optional_json(
            workspace / "artifacts/semantic_reviews" / f"rev_{int(revision):03d}.json"
        ) if isinstance(revision, int) else None,
        "hard_validator": load_optional_json(
            workspace / "artifacts/core_gate" / f"rev_{int(revision):03d}.json"
        ) if isinstance(revision, int) else None,
        "positive_qa": {
            "candidate_positives": evidence.get("candidate_positives", []),
            "validated_positives": evidence.get("validated_positives", []),
            "accepted": evidence.get("positives", []),
        },
        "negative_qa": evidence.get("mutants", []),
        "package": load_optional_json(workspace / "artifacts/package.json"),
    }


def run_candidate(workspace: Path, name: str, config: dict[str, Any], group: str,
                  parent: str | None = None, revision: int = 0) -> dict[str, Any]:
    command = [sys.executable, "-m", "verifier_trans.deterministic.replay.candidate", str(workspace),
               "--solution", name, "--group", group,
               "--timeout", str(config["experiment"].get("qa_timeout_seconds", 1800)),
               "--revision", str(revision)]
    if parent:
        command.extend(["--parent-solution", str(workspace / "run" / "validator" / parent)])
    rc, _ = run_script(command)
    path = workspace / "run" / "validator" / (f"{name}.{group}.json" if group != "all" else f"{name}.json")
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {
        "solution": name, "group": group, "accepted": None, "failure_cause": f"missing_result_rc_{rc}"
    }


def generate_solver(workspace: Path, config: dict[str, Any], credentials: dict[str, dict[str, str]],
                    name: str, mutation: bool = False, parent: str | None = None) -> str:
    output = workspace / "run" / "validator" / name
    # A model session can be interrupted after writing a complete candidate
    # payload but before emitting the sentinel. Preserve that payload and let
    # deterministic precheck decide whether it is usable; do not spend another
    # model request recreating an artifact that is already on disk.
    payload_root = output.resolve() if output.exists() else output
    payload_ready = payload_root.is_dir() and any(path.is_file() for path in payload_root.rglob("*"))
    if payload_ready:
        return "RECOVERED_EXISTING_CANDIDATE_PAYLOAD"
    reset_output(output)
    task = (
        "Create one task-relevant, runnable semantic mutant. Keep the known-valid parent behavior "
        "except for one behavior explicitly present in the frozen historical-F2P conversion plan, "
        "and write the complete replacement payload under /solution. "
        "Do not edit verifier/. " if mutation else
        "Create a structurally different but semantically correct implementation of the task. "
        "Write the complete repository-relative payload under /solution. "
    ) + "Then execute COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT."
    result = run_miniswe_session(
        project_root=PROJECT_ROOT, workspace=workspace,
        role="mutator" if mutation else "solver",
        prompt_path=prompt_path(config, "negative_generator" if mutation else "positive_generator"),
        credentials=role_credentials(credentials, "solver"), config=config, task=task,
        output_dir=output, trajectory_path=workspace / "artifacts" / "trajectories" / f"{name}.json",
        step_limit=session_step_cap(config, "mutator" if mutation else "solver"),
        parent_solution=(workspace / "run" / "validator" / parent) if parent else None,
    )
    payload_root = output.resolve() if output.exists() else output
    if not terminal_submission(result) and not (
        payload_root.is_dir() and any(path.is_file() for path in payload_root.rglob("*"))
    ):
        raise RuntimeError(f"{name} did not emit the explicit submission signal")
    return result


def reuse_infrastructure_failed_candidate(workspace: Path, name: str, mutation: bool) -> bool:
    """Reuse a generated candidate when only deterministic precheck failed.

    Candidate generation is an expensive model session.  If the candidate
    payload already exists and its recorded precheck failed because the replay
    harness was unavailable, retry the harness with the same payload instead
    of asking the model to recreate it.  Semantic failures never qualify.
    """
    root_name = "mutations" if mutation else "positives"
    precheck = workspace / "artifacts" / root_name / name / "precheck.json"
    payload = workspace / "run" / "validator" / name
    if not precheck.is_file() or not payload.is_dir():
        return False
    payload_root = payload.resolve() if payload.exists() else payload
    if not payload_root.is_dir() or not any(path.is_file() for path in payload_root.rglob("*")):
        return False
    try:
        document = json.loads(precheck.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    p2p = document.get("p2p") or {}
    excerpt = str(p2p.get("failure_excerpt") or "")
    all_results = json.dumps(document, ensure_ascii=False)
    return (
        p2p.get("failure_class") == "INFRASTRUCTURE"
        or "p2p_runner.py" in excerpt
        and ("No such file" in excerpt or "can't open file" in excerpt)
        or "uv_os_get_passwd" in all_results
    )


def adjudicate_solution(workspace: Path, config: dict[str, Any], credentials: dict[str, dict[str, str]],
                        name: str, mutation: bool, p2p: dict[str, Any],
                        parent: str | None = None, revision: int = 0) -> dict[str, Any]:
    evidence = {
        "instruction_scope": (workspace / "verifier/instruction_scope.md").read_text(encoding="utf-8"),
        "candidate": candidate_files(workspace / "run/validator" / name),
        "p2p_execution": p2p,
        "execution_precheck": p2p,
        "structural_precheck": structural_precheck(
            workspace, workspace / "run" / "validator" / name
        ),
        "parent": candidate_files(workspace / "run/validator" / parent) if parent else None,
        "gold_patch": ((workspace / "sealed/gold.patch").read_text(encoding="utf-8")
                       if not mutation else None),
        "final_converted_verifier_and_mapping": (
            verifier_tree(workspace / "verifier") if mutation else None
        ),
    }
    result = judge(
        config=config, credentials=credentials,
        role="mutation_judge" if mutation else "solution_judge",
        system=prompt_path(config, "mutation_judge" if mutation else "solution_judge")
        .read_text(encoding="utf-8"), evidence=evidence,
    )
    result = add_contract(
        workspace, revision, result,
        status=("PASS" if str(result.get("verdict", "")).upper() in
                {"VALID", "RELEVANT_NON_EQUIVALENT"} else "FAIL"),
        failure_class="NONE",
    )
    write_judgement(workspace / "artifacts" / ("mutations" if mutation else "positives") / name / "judge.json", result)
    return result


def replay_evidence(workspace: Path, config: dict[str, Any], evidence: dict[str, Any],
                    revision: int) -> dict[str, Any]:
    result = {"positives": [], "mutants": [], "accepted": True,
              "failure_class": "NONE"}
    for item in evidence.get("positives", []):
        p2p = run_candidate(workspace, item["name"], config, "p2p", revision=revision)
        f2p = run_candidate(workspace, item["name"], config, "f2p", revision=revision)
        legacy = run_candidate(workspace, item["name"], config, "legacy_f2p", revision=revision)
        contract = positive_execution_contract(p2p, f2p, legacy)
        item.update({key: value for key, value in contract.items() if key != "accepted"})
        row = {"name": item["name"], "p2p": p2p, "f2p": f2p, "legacy_f2p": legacy, **contract,
               "passed": contract["accepted"]}
        result["positives"].append(row)
        result["accepted"] = result["accepted"] and row["passed"]
        if not row["passed"]:
            failed = [p2p, f2p]
            if any(candidate_infra_failure(item) for item in failed):
                result["failure_class"] = "INFRASTRUCTURE"
                result["failure_domain"] = "infrastructure"
            elif result["failure_class"] == "NONE":
                result["failure_class"] = "VERIFIER_SEMANTIC"
    for item in evidence.get("mutants", []):
        p2p = run_candidate(workspace, item["name"], config, "p2p", item.get("parent"), revision)
        f2p = run_candidate(workspace, item["name"], config, "f2p", item.get("parent"), revision)
        contract = negative_execution_contract(
            bool(item.get("judge", {}).get("verdict", "").upper() == "RELEVANT_NON_EQUIVALENT"),
            p2p, f2p,
        )
        row = {"name": item["name"], "p2p": p2p, "f2p": f2p, **contract,
               "passed": contract["accepted"]}
        result["mutants"].append(row)
        result["accepted"] = result["accepted"] and row["passed"]
        if not row["passed"]:
            failed = [p2p, f2p]
            if any(candidate_infra_failure(item) for item in failed):
                result["failure_class"] = "INFRASTRUCTURE"
                result["failure_domain"] = "infrastructure"
            elif result["failure_class"] == "NONE":
                result["failure_class"] = "VERIFIER_SEMANTIC"
    return result


def _relative_evidence(value: Any, workspace: Path) -> Any:
    """Remove host paths before evidence is placed in a model task prompt."""
    root = workspace.resolve()
    if isinstance(value, dict):
        return {key: _relative_evidence(item, workspace) for key, item in value.items()}
    if isinstance(value, list):
        return [_relative_evidence(item, workspace) for item in value]
    if isinstance(value, str):
        candidate = Path(value)
        try:
            return str(candidate.resolve().relative_to(root))
        except (OSError, ValueError):
            return value
    return value


def repair_packet(workspace: Path, check: dict[str, Any], qa: dict[str, Any], reason: str) -> dict[str, Any]:
    """Build evidence-led repair instructions with the canonical artifact shape.

    Sanity failures are deterministic, but a model repair session still needs the
    typed handoff contract.  In particular, ``manifest.test_files`` must be a
    list of ``{source, target}`` objects; repeating only the error names caused
    fresh sessions to reproduce the same bare-string manifest.
    """
    errors = []
    for payload in (check, qa):
        if isinstance(payload, dict):
            errors.extend(str(item) for item in payload.get("errors") or ())
            nested = payload.get("sanity")
            if isinstance(nested, dict):
                errors.extend(str(item) for item in nested.get("errors") or ())
    artifact_hint = (
        " For artifact-schema repairs, rewrite manifest.json so test_files is a "
        "non-empty JSON list of objects, each with repository-relative source and "
        "target (for example [{\"source\":\"verifier.py\","
        "\"target\":\"verifier/verifier.py\"}]); set functional_artifact "
        "to an existing declared source, and declare every executable artifact file."
        if any("manifest_test_files" in error or "functional_verifier_source" in error
               or "undeclared_verifier_file" in error for error in errors)
        else ""
    )
    return {"reason": reason, "core_gate": _relative_evidence(check, workspace),
            "qa_failure": _relative_evidence(qa, workspace),
            "instruction": "Repair only the verifier; preserve valid accumulated evidence." + artifact_hint}


def automatic_terminal_state(final: dict[str, Any]) -> str:
    """Map a finished attempt to a machine-readable terminal state.

    The controller repairs semantic verifier defects within its bounded revision
    loop. Once the loop ends, every outcome is explicit; there is no implicit
    human-review queue in the conversion path.
    """
    if final.get("accepted") is True:
        return "FINAL_VALIDATED"
    domain = str(final.get("failure_domain") or "failed").lower()
    if domain == "infrastructure":
        return "INFRASTRUCTURE"
    if domain.startswith("package"):
        return "PACKAGE"
    return "FAILED"


def non_retryable_model_endpoint_error(error: Exception) -> bool:
    """Return True for account/auth/policy failures that retries cannot repair.

    These errors are emitted by model adapters as RuntimeError text. Treating them
    as Converter failures would consume verifier revisions and obscure the actual
    infrastructure outage. Transient 429/5xx responses remain retryable.
    """
    message = str(error).lower()
    if "model api returned http" not in message:
        return False
    return any(
        marker in message
        for marker in (
            "http 400",
            "http 401",
            "http 402",
            "http 403",
            "http 404",
            "insufficient balance",
            "authentication",
            "invalid api key",
            "permission denied",
        )
    )


def recover_partial_converter_artifact(workspace: Path, error: Exception) -> dict[str, Any] | None:
    """Promote a failed Converter staging payload into an evidence-led repair.

    A model session can hit its tool-step ceiling after writing useful verifier
    files but before the explicit submission sentinel.  Treating that as a
    fresh BUILD discards the expensive work and repeats the same exploration.
    The session handoff already filters scratch trees, so the newest staging
    directory is safe construction evidence for the same Converter REPAIR.
    """
    staging_root = workspace / "artifacts" / "staging"
    candidates = sorted(
        (path for path in staging_root.glob("converter_rev_*") if path.is_dir()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    ) if staging_root.is_dir() else []
    partial = next((path for path in candidates if any(path.rglob("*"))), None)
    if partial is None:
        return None
    reset_output(workspace / "verifier")
    copy_tree(partial, workspace / "verifier")
    return repair_packet(
        workspace,
        {"failure_domain": "converter", "error": repr(error),
         "partial_staging": str(partial),
         "partial_files": sorted(str(path.relative_to(partial)) for path in partial.rglob("*") if path.is_file())},
        {},
        "The previous Converter session stopped before submission; repair and complete its partial verifier artifact.",
    )


def run_pipeline(args: argparse.Namespace) -> int:
    """Run one controller under an attempt-scoped lease."""
    requested_workspace = args.workspace.resolve()
    try:
        workspace = attempt_from_path(requested_workspace).runtime
    except ValueError:
        workspace = requested_workspace
    with controller_session_lock(workspace):
        try:
            return _run_pipeline(args)
        except KeyboardInterrupt:
            append_event(workspace, "INTERRUPTED", "controller", reason="KeyboardInterrupt")
            raise


def _run_pipeline(args: argparse.Namespace) -> int:
    if not args.allow_external_model_data:
        raise SystemExit(
            "refusing to start model-backed conversion without "
            "--allow-external-model-data"
        )
    requested_workspace = args.workspace.resolve()
    try:
        workspace = attempt_from_path(requested_workspace).runtime
    except ValueError:
        # Keep deterministic modules usable with isolated legacy-shaped test
        # fixtures while all CLI-created runs use the classified layout.
        workspace = requested_workspace
    config, credentials = load_config(args.config), load_credentials(args.credentials)
    max_revisions = int(config["experiment"].get("max_verifier_revisions", 3))
    meta_path = workspace / "run/metadata.json"
    if not meta_path.is_file():
        raise SystemExit(f"unprepared workspace: {workspace}")
    preflight_path = workspace / "run/source_preflight.json"
    if not preflight_path.is_file() or json.loads(preflight_path.read_text(encoding="utf-8")).get("status") != "PASS":
        raise SystemExit(f"source preflight is not PASS: {preflight_path}")
    environment_path = workspace / "run/environment_preflight.json"
    if not environment_path.is_file() or json.loads(environment_path.read_text(encoding="utf-8")).get("status") != "PASS":
        raise SystemExit(f"environment preflight is not PASS: {environment_path}")
    existing_final = workspace / "run/final.json"
    if args.resume and existing_final.is_file():
        final = json.loads(existing_final.read_text(encoding="utf-8"))
        if final.get("accepted") is True:
            evidence = load_evidence(workspace)
            positive_contract_ok = bool(evidence.get("positives")) and all(
                item.get("contract_version") == POSITIVE_CONTRACT_VERSION
                and item.get("current_f2p_pass") is True
                and item.get("p2p_pass") is True
                for item in evidence.get("positives", [])
            )
            if not positive_contract_ok:
                append_event(workspace, "QA_REVALIDATE", "positive_current_contract")
            else:
                # A previous controller may have completed package smoke but
                # been interrupted before refreshing report phases.  Rebuild
                # the summary from the authoritative artifacts before
                # returning.
                report = load_optional_json(workspace / "run/report.json") or {}
                report.update({
                    "status": "VERIFIED",
                    "state": "PACKAGED" if (load_optional_json(workspace / "artifacts/package.json") or {}).get("smoke_returncode") == 0 else "FINAL_VALIDATED",
                    "failure_class": "NONE",
                    "final": final,
                    "evidence": evidence,
                    "workspace": str(workspace),
                    "phases": phase_summary(workspace, final, evidence),
                })
                save_json(workspace / "run/report.json", report)
                save_json(workspace / "state.json", {
                    "state": report["state"],
                    "last_node": "package_smoke" if report["state"] == "PACKAGED" else "final_validated",
                    "updated_at_utc": utc(),
                    "revision": final.get("revision"),
                })
                write_report(workspace)
                print(json.dumps({"status": "VERIFIED", "resumed": True, "final": final}, ensure_ascii=False, indent=2))
                return 0
    append_event(workspace, "PREPARED", "controller_start",
                 instance_id=json.loads(meta_path.read_text(encoding="utf-8"))["instance_id"])
    loaded_evidence = load_evidence(workspace)
    stale_positives = [item for item in loaded_evidence.get("positives", [])
                       if item.get("contract_version") != POSITIVE_CONTRACT_VERSION]
    evidence = {
        # Stale positives remain on disk as audit history, but must not count
        # toward the new hard contract before their payload is re-prechecked.
        "positives": [
            item for item in loaded_evidence.get("positives", [])
            if item.get("contract_version") == POSITIVE_CONTRACT_VERSION
        ],
        "mutants": list(loaded_evidence.get("mutants", [])),
        "candidate_positives": list(loaded_evidence.get("candidate_positives", [])),
        "validated_positives": list(loaded_evidence.get("validated_positives", [])),
    }
    if stale_positives:
        # Keep old candidate payloads and re-run them under the current
        # contract; do not silently promote their historical gate result.
        append_event(workspace, "QA_REVALIDATE", "positive_current_contract",
                     count=len(stale_positives), names=[item.get("name") for item in stale_positives])
        save_evidence(workspace, evidence)
    packet = None
    if args.repair_packet is not None:
        packet_path = args.repair_packet.resolve()
        try:
            loaded_packet = json.loads(packet_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"invalid repair packet: {packet_path}: {exc}") from exc
        if not isinstance(loaded_packet, dict):
            raise SystemExit(f"repair packet must be a JSON object: {packet_path}")
        packet = loaded_packet
        append_event(
            workspace,
            "REPAIR_REQUESTED",
            "external_repair_packet",
            source=str(packet_path),
            reason=str(packet.get("reason", "explicit evidence-led repair")),
        )
    revision_dirs = sorted((workspace / "artifacts/verifier").glob("rev_[0-9][0-9][0-9]"))
    resume_revision: int | None = None
    recovery_error: dict[str, Any] | None = None
    if args.resume and (workspace / "verifier/manifest.json").is_file():
        # A session can be interrupted after Converter submission but before
        # the snapshot/semantic gate. Recover the live submitted artifact
        # deterministically. Comparing the digest is essential: otherwise a
        # live rev4 artifact can be mislabeled as the latest immutable rev3,
        # causing repeated Semantic Judge calls against the wrong revision.
        try:
            latest_revision = max(
                (int(path.name.split("_")[-1]) for path in revision_dirs),
                default=0,
            )
            latest_snapshot = load_optional_json(
                workspace / "artifacts/verifier" / f"rev_{latest_revision:03d}.json"
            ) if latest_revision else None
            live_hash = file_digest(workspace / "verifier")
            live_is_new = (
                not latest_snapshot
                or live_hash != latest_snapshot.get("verifier_hash")
            )
            recovery_revision = latest_revision + 1 if live_is_new else latest_revision
            if not live_is_new:
                recovery_revision = None
            recovered_sanity = (
                run_sanity(workspace, recovery_revision)
                if recovery_revision is not None else {"status": "PASS"}
            )
            if recovery_revision is not None and recovered_sanity.get("status") == "PASS" and self_review_passed(workspace):
                snapshot_verifier(workspace, recovery_revision)
                revision_dirs = sorted((workspace / "artifacts/verifier").glob("rev_[0-9][0-9][0-9]"))
                resume_revision = recovery_revision
                append_event(workspace, "RESUMED_EXISTING", f"verifier_rev_{recovery_revision}", revision=recovery_revision,
                             reason="live submitted verifier had no matching immutable snapshot")
            elif recovery_revision is not None:
                recovery_error = {"sanity": recovered_sanity,
                                  "reason": "submitted verifier could not be recovered deterministically"}
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            recovery_error = {"reason": "submitted verifier recovery failed", "error": repr(exc)}
    if args.resume and revision_dirs:
        resume_revision = max(int(path.name.split("_")[-1]) for path in revision_dirs)
    start_revision = resume_revision or (max((int(path.name.split("_")[-1]) for path in revision_dirs), default=0) + 1)
    final: dict[str, Any] = {"accepted": False}
    if recovery_error is not None:
        final = {"accepted": False, "failure_domain": "artifact_schema", **recovery_error}
        append_event(workspace, "ARTIFACT_SCHEMA", "resume_recovery", **recovery_error)
        # A submitted artifact may be present even when deterministic recovery
        # cannot snapshot it.  Route the concrete sanity evidence through the
        # normal single-Converter REPAIR path; restarting BUILD would discard
        # the accumulated diagnosis and can produce the same invalid contract.
        packet = repair_packet(
            workspace,
            recovery_error.get("sanity") or recovery_error,
            {},
            "deterministic recovery rejected the submitted verifier artifact",
        )

    for revision in range(start_revision, max_revisions + start_revision):
        validating_existing = resume_revision == revision
        append_event(
            workspace,
            "VALIDATING_EXISTING" if validating_existing else "CONVERTING",
            f"verifier_rev_{revision}" if validating_existing else f"converter_rev_{revision}",
            revision=revision, repair=bool(packet), existing=validating_existing,
        )
        try:
            if not validating_existing:
                run_converter(workspace, config, credentials, revision, packet)
                append_event(workspace, "CONVERTER_SUBMITTED", f"converter_rev_{revision}_submit",
                             revision=revision, submission_round=revision)
            if not self_review_passed(workspace):
                final = {"accepted": False, "failure_domain": "artifact_schema",
                         "reason": "converter self-review missing or failed", "revision": revision}
                append_event(workspace, "ARTIFACT_SCHEMA", f"self_review_rev_{revision}")
                break
            normalize_manifest_artifact(workspace, revision)
            sanity = run_sanity(workspace, revision)
            if sanity.get("status") != "PASS":
                final = {"accepted": False, "failure_domain": "artifact_schema",
                         "reason": "verifier artifact sanity check failed",
                         "revision": revision, "sanity": sanity}
                append_event(workspace, "ARTIFACT_SCHEMA", f"sanity_rev_{revision}", errors=sanity.get("errors", []))
                packet = repair_packet(
                    workspace, sanity, {},
                    "verifier artifact violates the deterministic execution contract",
                )
                continue
            # A prior revision may have populated `packet` to request repair.
            # Once this revision passes sanity, that stale diagnosis must not
            # leak into the QA phase and turn a successful candidate into a
            # false QA_DEFECT.
            packet = None
            semantic = (
                reusable_revision_evidence(
                    workspace,
                    workspace / "artifacts/semantic_reviews" / f"rev_{revision:03d}.json",
                    revision,
                    kind="semantic",
                )
                if validating_existing else None
            )
            if semantic is not None:
                append_event(workspace, "REUSED_VALIDATION", f"semantic_rev_{revision}",
                             revision=revision, evidence="semantic_review")
            semantic_retries = 0
            semantic_retry_limit = int(config["experiment"].get("infra_retry_limit", 1))
            while semantic is None:
                try:
                    semantic = run_verifier_judge(workspace, config, credentials, revision)
                except Exception as exc:
                    if semantic_retries < semantic_retry_limit:
                        semantic_retries += 1
                        append_event(workspace, "INFRA_RETRY", f"semantic_rev_{revision}",
                                     revision=revision, attempt=semantic_retries,
                                     limit=semantic_retry_limit, error=repr(exc))
                        continue
                    final = {"accepted": False, "failure_domain": "infrastructure",
                             "failure_class": "INFRASTRUCTURE", "revision": revision,
                             "reason": "semantic judge execution failed", "error": repr(exc),
                             "attempts": semantic_retries + 1}
                    append_event(workspace, "INFRASTRUCTURE", f"semantic_rev_{revision}",
                                 attempts=semantic_retries + 1, error=repr(exc))
                    break
            if semantic is None:
                break
            if str(semantic.get("verdict", "REPAIR")).upper() != "PASS":
                packet = repair_packet(workspace, {}, {"semantic": semantic}, "Semantic Judge requested verifier repair")
                append_event(workspace, "SEMANTIC_VERIFIER", f"semantic_rev_{revision}")
                continue
            if not validating_existing:
                snapshot_verifier(workspace, revision)
        except Exception as exc:
            if non_retryable_model_endpoint_error(exc):
                final = {
                    "accepted": False,
                    "failure_domain": "infrastructure",
                    "failure_class": "MODEL_ENDPOINT",
                    "retryable": False,
                    "reason": "non-retryable model endpoint failure",
                    "error": repr(exc),
                    "revision": revision,
                }
                append_event(workspace, "INFRASTRUCTURE", f"model_endpoint_rev_{revision}",
                             revision=revision, failure_class="MODEL_ENDPOINT",
                             retryable=False, error=repr(exc))
                break
            final = {"accepted": False, "failure_domain": "converter", "error": repr(exc)}
            partial_packet = recover_partial_converter_artifact(workspace, exc)
            if partial_packet is not None:
                packet = partial_packet
                append_event(workspace, "CONVERTER_REPAIR", f"converter_rev_{revision}_partial",
                             revision=revision, error=repr(exc),
                             partial_files=len(partial_packet["core_gate"].get("partial_files", [])))
            else:
                append_event(workspace, "FAILED", f"converter_rev_{revision}_error", error=repr(exc))
            continue

        check = (
            reusable_revision_evidence(
                workspace,
                workspace / "artifacts/core_gate" / f"rev_{revision:03d}.json",
                revision,
                kind="hard",
            )
            if validating_existing else None
        )
        if check is not None:
            append_event(workspace, "REUSED_VALIDATION", f"core_rev_{revision}",
                         revision=revision, evidence="hard_validator")
        else:
            append_event(workspace, "HARD_VALIDATING", f"core_rev_{revision}", revision=revision)
            infra_retries = 0
            infra_retry_limit = int(config["experiment"].get("infra_retry_limit", 1))
            while True:
                try:
                    check = run_hard_validator(workspace, config, revision)
                except Exception as exc:
                    check = {"accepted": False, "failure_domain": "infrastructure",
                             "failure_class": "INFRASTRUCTURE", "reason": repr(exc)}
                if check.get("accepted") or not infra_failure(check) or infra_retries >= infra_retry_limit:
                    break
                infra_retries += 1
                append_event(workspace, "INFRA_RETRY", f"core_rev_{revision}",
                             revision=revision, attempt=infra_retries,
                             limit=infra_retry_limit)
        if not check.get("accepted"):
            final = {"accepted": False, "core": check}
            if infra_failure(check):
                final["failure_domain"] = "infrastructure"
                final["failure_class"] = "INFRASTRUCTURE"
                append_event(workspace, "INFRASTRUCTURE", f"core_rev_{revision}",
                             attempts=infra_retries + 1)
                break
            packet = repair_packet(workspace, check, {}, "Core Gate rejected the verifier")
            append_event(workspace, "SEMANTIC_VERIFIER", f"core_rev_{revision}")
            continue
        append_event(workspace, "HARD_VALIDATED", f"core_rev_{revision}", revision=revision)

        replay_retries = 0
        replay_retry_limit = int(config["experiment"].get("infra_retry_limit", 1))
        while True:
            replay = replay_evidence(workspace, config, evidence, revision)
            if (replay.get("accepted") or
                    replay.get("failure_class") != "INFRASTRUCTURE" or
                    replay_retries >= replay_retry_limit):
                break
            replay_retries += 1
            append_event(workspace, "INFRA_RETRY", f"evidence_replay_rev_{revision}",
                         revision=revision, attempt=replay_retries,
                         limit=replay_retry_limit)
        save_json(workspace / "artifacts/core_gate" / f"evidence_replay_rev_{revision:03d}.json", replay)
        save_evidence(workspace, evidence)
        if not replay["accepted"]:
            if replay.get("failure_class") == "INFRASTRUCTURE":
                final = {"accepted": False, "failure_domain": "infrastructure",
                         "failure_class": "INFRASTRUCTURE", "core": check,
                         "evidence_replay": replay, "revision": revision,
                         "attempts": replay_retries + 1}
                append_event(workspace, "INFRASTRUCTURE", f"evidence_replay_rev_{revision}",
                             attempts=replay_retries + 1)
                break
            final = {"accepted": False, "core": check, "evidence_replay": replay}
            packet = repair_packet(workspace, check, replay, "latest verifier broke accumulated QA evidence")
            append_event(workspace, "REPAIR", f"evidence_replay_rev_{revision}")
            continue
        append_event(workspace, "QA", f"qa_rev_{revision}", revision=revision,
                     accumulated_positive=len(evidence["positives"]),
                     accumulated_mutants=len(evidence["mutants"]))

        positive_target = int(config["experiment"].get("valid_positive_target", 1))
        append_event(workspace, "QA_POSITIVE", f"positive_rev_{revision}", target=positive_target)
        qa_failure: dict[str, Any] | None = None
        for attempt in range(1, int(config["experiment"].get("max_positive_attempts", 3)) + 1):
            if len(evidence["positives"]) >= positive_target:
                break
            # Each attempt gets a fresh output directory.  Solver containers
            # may write the mounted payload as a different uid, so retrying
            # the same name can make host-side reset_output fail with
            # PermissionError.  Keep failed attempts immutable and namespace
            # the accepted candidate by its attempt number.
            name = f"positive_{len(evidence['positives']) + 1}_attempt_{attempt}"
            try:
                if not reuse_infrastructure_failed_candidate(workspace, name, False):
                    generate_solver(workspace, config, credentials, name)
                else:
                    append_event(workspace, "QA_CANDIDATE_REUSE", name,
                                 reason="previous deterministic precheck infrastructure failure")
                p2p = run_candidate(workspace, name, config, "p2p", revision=revision)
                f2p = run_candidate(workspace, name, config, "f2p", revision=revision)
                legacy = run_candidate(workspace, name, config, "legacy_f2p", revision=revision)
                precheck = {
                    "name": name, "p2p": p2p, "f2p": f2p, "legacy_f2p": legacy,
                    "runnable": all(
                        result.get("runnable") is True
                        for result in (p2p, f2p)
                    ),
                    "current_f2p_pass": f2p.get("accepted") is True,
                    "historical_f2p_runnable": legacy.get("runnable") is True,
                    "historical_f2p_pass": legacy.get("accepted") is True if legacy.get("runnable") is True else None,
                    "legacy_f2p_separation": (
                        legacy.get("runnable") is True and legacy.get("accepted") is False
                    ),
                    "original_p2p_pass": p2p.get("accepted") is True,
                }
                structure = structural_precheck(
                    workspace, workspace / "run" / "validator" / name
                )
                precheck["structural"] = structure
                candidate_contract = positive_candidate_contract(
                    p2p, f2p, legacy, structure
                )
                precheck["candidate_contract"] = candidate_contract
                save_json(workspace / "artifacts/positives" / name / "precheck.json", precheck)
                if not candidate_contract["eligible_for_adjudication"]:
                    continue

                candidate_record = {
                    "name": name,
                    "verifier_revision": revision,
                    "status": "candidate_positive",
                    "precheck": candidate_contract,
                    "p2p": p2p,
                    "f2p": f2p,
                    "legacy_f2p": legacy,
                }
                evidence["candidate_positives"].append(candidate_record)
                save_evidence(workspace, evidence)
                execution = {"p2p": p2p, "f2p": f2p, "legacy_f2p": legacy}
                adjudication = adjudicate_solution(
                    workspace, config, credentials, name, False, execution, revision=revision
                )
                judge_valid = str(adjudication.get("verdict", "UNCERTAIN")).upper() == "VALID"

                # Re-run the complete deterministic contract after semantic
                # adjudication.  The Judge decides whether this is a
                # legitimate alternative implementation; only this replay
                # decides whether the current verifier accepts it.
                p2p = run_candidate(workspace, name, config, "p2p", revision=revision)
                f2p = run_candidate(workspace, name, config, "f2p", revision=revision)
                legacy = run_candidate(workspace, name, config, "legacy_f2p", revision=revision)
                validated = validated_positive_contract(judge_valid, p2p, f2p, legacy)
                validated_record = {
                    "name": name, "verifier_revision": revision,
                    "verifier_hash": adjudication.get("verifier_hash"),
                    **validated, "judge": adjudication,
                    "p2p": p2p, "f2p": f2p, "legacy_f2p": legacy,
                }
                if judge_valid:
                    evidence["validated_positives"].append(validated_record)
                candidate_record["judge"] = adjudication
                candidate_record["post_judge"] = validated_record
                save_evidence(workspace, evidence)

                if validated["hard_false_negative"]:
                    packet = repair_packet(
                        workspace,
                        check,
                        {"validated_positive": validated_record},
                        "validated positive rejected by current verifier",
                    )
                    append_event(
                        workspace, "VERIFIER_FALSE_NEGATIVE", f"positive_{name}",
                        revision=revision, candidate=name,
                    )
                    break
                if not validated["accepted"]:
                    continue
                contract = positive_execution_contract(p2p, f2p, legacy)
                evidence["positives"].append({
                    "name": name, "verifier_revision": revision,
                    "verifier_hash": adjudication.get("verifier_hash"),
                    **contract,
                    "judge": adjudication,
                })
                save_evidence(workspace, evidence)
            except Exception as exc:
                save_json(workspace / "artifacts/positives" / f"attempt_{attempt}.error.json", {"error": repr(exc)})
                if non_retryable_model_endpoint_error(exc):
                    qa_failure = {
                        "accepted": False, "failure_domain": "infrastructure",
                        "failure_class": "MODEL_ENDPOINT", "retryable": False,
                        "reason": "non-retryable model endpoint failure during positive QA",
                        "error": repr(exc), "revision": revision,
                    }
                    append_event(workspace, "INFRASTRUCTURE", f"positive_rev_{revision}",
                                 failure_class="MODEL_ENDPOINT", retryable=False, error=repr(exc))
                    break
        if qa_failure:
            final = qa_failure
            break
        if packet:
            append_event(workspace, "QA_DEFECT", f"positive_rev_{revision}")
            continue
        if len(evidence["positives"]) < positive_target:
            final = {"accepted": False, "failure_domain": "candidate", "reason": "no adjudicated valid positive"}
            append_event(workspace, "BUDGET_EXHAUSTED", "positive_generation", target=positive_target)
            break

        mutant_target = int(config["experiment"].get("eligible_mutant_target", 2))
        parent = evidence["positives"][0]["name"]
        append_event(workspace, "QA_NEGATIVE", f"negative_rev_{revision}", target=mutant_target)
        qa_failure = None
        for attempt in range(1, int(config["experiment"].get("max_mutation_attempts", 5)) + 1):
            if len(evidence["mutants"]) >= mutant_target:
                break
            # See the positive QA attempt naming above: never reuse a mounted
            # solver output directory across retries.
            name = f"mutant_{len(evidence['mutants']) + 1}_attempt_{attempt}"
            try:
                if not reuse_infrastructure_failed_candidate(workspace, name, True):
                    generate_solver(workspace, config, credentials, name, mutation=True, parent=parent)
                else:
                    append_event(workspace, "QA_CANDIDATE_REUSE", name,
                                 reason="previous deterministic precheck infrastructure failure")
                p2p = run_candidate(workspace, name, config, "p2p", parent, revision)
                precheck = {"name": name, "parent": parent, "p2p": p2p,
                            "runnable": p2p.get("runnable") is True,
                            "original_p2p_pass": p2p.get("accepted") is True}
                save_json(workspace / "artifacts/mutations" / name / "precheck.json", precheck)
                if not precheck["runnable"] or not precheck["original_p2p_pass"]:
                    continue
                adjudication = adjudicate_solution(
                    workspace, config, credentials, name, True, p2p, parent, revision
                )
                if str(adjudication.get("verdict", "UNCERTAIN")).upper() == "RELEVANT_NON_EQUIVALENT" and p2p.get("accepted") is True:
                    evidence["mutants"].append({
                        "name": name, "parent": parent, "verifier_revision": revision,
                        "verifier_hash": adjudication.get("verifier_hash"),
                        "judge": adjudication,
                    })
                    save_evidence(workspace, evidence)
                    f2p = run_candidate(workspace, name, config, "f2p", parent, revision)
                    contract = negative_execution_contract(True, p2p, f2p)
                    evidence["mutants"][-1].update({"f2p": f2p, **contract})
                    save_evidence(workspace, evidence)
                    if contract["repair_required"]:
                        packet = repair_packet(workspace, check, {"mutant": {"name": name, "f2p": f2p, "judge": adjudication, **contract}}, "eligible semantic mutant passed verifier")
                    elif contract["infrastructure_failure"]:
                        append_event(workspace, "QA_INFRASTRUCTURE_FAILURE", name, failure_class="INFRASTRUCTURE")
                        break
            except Exception as exc:
                save_json(workspace / "artifacts/mutations" / f"attempt_{attempt}.error.json", {"error": repr(exc)})
                if non_retryable_model_endpoint_error(exc):
                    qa_failure = {
                        "accepted": False, "failure_domain": "infrastructure",
                        "failure_class": "MODEL_ENDPOINT", "retryable": False,
                        "reason": "non-retryable model endpoint failure during negative QA",
                        "error": repr(exc), "revision": revision,
                    }
                    append_event(workspace, "INFRASTRUCTURE", f"negative_rev_{revision}",
                                 failure_class="MODEL_ENDPOINT", retryable=False, error=repr(exc))
                    break
        if qa_failure:
            final = qa_failure
            break
        if packet:
            append_event(workspace, "QA_DEFECT", f"negative_rev_{revision}")
            continue
        if len(evidence["mutants"]) < mutant_target:
            final = {"accepted": False, "failure_domain": "mutation", "reason": "not enough adjudicated semantic mutants"}
            append_event(workspace, "BUDGET_EXHAUSTED", "mutation_generation", target=mutant_target)
            break

        final = {"accepted": True, "revision": revision, "core": check,
                 "positive_count": len(evidence["positives"]), "mutant_count": len(evidence["mutants"])}
        append_event(workspace, "FINAL_VALIDATED", f"revision_{revision}", **final)
        break

    save_evidence(workspace, evidence)
    save_json(workspace / "run/final.json", final)
    accepted = final.get("accepted") is True
    terminal_state = automatic_terminal_state(final)
    report = {"status": "VERIFIED" if accepted else terminal_state,
              "state": terminal_state,
              "failure_class": final.get("failure_class") or (
                  "NONE" if accepted else "VERIFIER_SEMANTIC"
              ),
              "final": final, "evidence": evidence, "workspace": str(workspace),
              "phases": phase_summary(workspace, final, evidence)}
    save_json(workspace / "run/report.json", report)
    write_report(workspace)
    if final.get("accepted"):
        rc, output = run_script([
            sys.executable, "-m", "verifier_trans.deterministic.packaging.package_task", str(workspace)
        ])
        if rc != 0:
            save_json(workspace / "artifacts/package.json", {"returncode": rc, "output": output[-4000:]})
            final = {**final, "accepted": False, "failure_domain": "package", "reason": "package build failed"}
            save_json(workspace / "run/final.json", final)
            report["final"] = final
            report["status"], report["state"] = "PACKAGE", "PACKAGE"
            report["phases"] = phase_summary(workspace, final, evidence)
            save_json(workspace / "run/report.json", report)
            write_report(workspace)
            return 1
        smoke_rc, smoke_output = run_script([
            sys.executable, "-m", "verifier_trans.deterministic.packaging.package_smoke", str(workspace),
            "--timeout", str(config["experiment"].get("package_smoke_timeout_seconds", 1800)),
        ])
        save_json(workspace / "artifacts/package.json", {
            "package_returncode": rc, "package_output": output[-4000:],
            "smoke_returncode": smoke_rc, "smoke_output": smoke_output[-4000:],
        })
        if smoke_rc != 0:
            final = {**final, "accepted": False, "failure_domain": "package_smoke",
                     "reason": "package smoke test failed"}
            save_json(workspace / "run/final.json", final)
            report["final"] = final
            report["status"], report["state"] = "PACKAGE", "PACKAGE"
            report["phases"] = phase_summary(workspace, final, evidence)
            save_json(workspace / "run/report.json", report)
            write_report(workspace)
            return 1
        append_event(workspace, "PACKAGED", "package_smoke", revision=final.get("revision"))
        published = publish_final_task(workspace, int(final["revision"]))
        report["state"] = "PACKAGED"
        report["final_task"] = str(published)
        report["phases"] = phase_summary(workspace, final, evidence)
        save_json(workspace / "run/report.json", report)
        write_report(workspace)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "VERIFIED" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    def add_run_arguments(command_parser: argparse.ArgumentParser) -> None:
        source = command_parser.add_mutually_exclusive_group(required=True)
        source.add_argument("--workspace", type=Path, help="attempt directory (or its .compat view)")
        source.add_argument("--instance-id", help="use the latest prepared attempt for this instance")
        command_parser.add_argument("--runs-root", type=Path, default=DEFAULT_RUNS_ROOT)
        command_parser.add_argument(
            "--credentials", "--env-file", dest="credentials", type=Path, default=DEFAULT_ENV
        )
        command_parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
        command_parser.add_argument(
            "--allow-external-model-data", action="store_true",
            help="explicitly allow task/repository context to be sent to the configured model service",
        )
        command_parser.add_argument(
            "--repair-packet", type=Path,
            help=(
                "JSON evidence packet for an explicit Converter REPAIR; starts "
                "the next verifier revision from the latest immutable evidence"
            ),
        )

    run = sub.add_parser("run", help="run conversion on a prepared attempt")
    add_run_arguments(run)
    run.add_argument("--no-resume", dest="resume", action="store_false",
                     help="start a new verifier revision instead of using existing artifacts")
    run.set_defaults(resume=True)
    resume = sub.add_parser("resume", help="resume the latest prepared conversion attempt")
    add_run_arguments(resume)
    resume.set_defaults(resume=True)
    prepare = sub.add_parser("prepare", help="prepare one workspace from SWE-Pro parquet")
    prepare.add_argument("--data", type=Path, default=Path("/lg-home/cog8/lwli6/Data/swebench_pro/test-00000-of-00001.parquet"))
    prepare.add_argument("--instance-id")
    prepare.add_argument("--row-index", type=int)
    prepare.add_argument("--runs-root", type=Path, default=DEFAULT_RUNS_ROOT)
    prepare.add_argument("--materialize-repo", action="store_true")
    prepare.add_argument("--local-repos-root", type=Path, default=Path("/tmp/vc_scratch/repos"))
    prepare.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()
    if args.command == "prepare":
        # Fail closed on shell-expansion mistakes or stale dataset paths.
        # Path("") resolves to the current directory, which otherwise lets the
        # preparation worker silently select an unrelated/default input.
        data_path = args.data.expanduser()
        if not data_path.is_file():
            raise SystemExit(f"prepare data file does not exist: {data_path}")
        command = [sys.executable, "-m", "verifier_trans.deterministic.preparation.prepare_instance",
                   "--data", str(data_path.resolve()),
                   "--runs-root", str(args.runs_root.resolve()),
                   "--timeout", str(args.timeout)]
        if args.instance_id:
            command.extend(["--instance-id", args.instance_id])
        if args.row_index is not None:
            command.extend(["--row-index", str(args.row_index)])
        if args.materialize_repo:
            command.append("--materialize-repo")
        if args.local_repos_root:
            command.extend(["--local-repos-root", str(args.local_repos_root.resolve())])
        return run_script(command)[0]
    if args.workspace is None:
        args.workspace = RunLayout.for_instance(args.runs_root, args.instance_id).latest_attempt().root
    if args.repair_packet is not None:
        # An explicit evidence-led repair must not resume QA against the old
        # revision. It starts the next revision through the same Converter.
        args.resume = False
    return run_pipeline(args)


if __name__ == "__main__":
    raise SystemExit(main())
