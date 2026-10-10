#!/usr/bin/env python3
"""Prepare one SWE-Pro instance into a permission-partitioned workspace.

Stage A of the conversion framework.  Everything in this script is
deterministic — no model is called.  It produces the evidence package that the
agent roles in stage B work from, and it is precisely where the information
boundary between those roles is established:

    public/     repo checkout, problem_statement, interface contract subset
    restricted/ original tests, test patch, f2p/p2p seeds, test_patch metadata
    sealed/     Gold/Requirements/Interface construction evidence; Converter-only
    verifier/   verifier builder output
    run/        audit evidence, replay logs, reports

Two upstream fields are deliberately kept out of the solver-visible ``public/``
bundle. ``requirements`` and the raw ``interface`` may encode Gold-derived
helpers or paths. The Converter may inspect them as labelled
construction evidence, while the final solver and candidate generators cannot.
``interface.md`` is also reduced to a public contract subset via
:func:`extract_contract`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ...paths import DEFAULT_RUNS_ROOT, PROJECT_ROOT, RunLayout
from ..execution import discover_execution_spec, execution_spec_hash
from .common import (
    as_list,
    build_base_state_script,
    checkout_commit,
    extract_contract,
    image_ref,
    normalize_node_id,
    normalize_repo_path,
    parse_instance_id,
    resolve_repo_test_path,
    safe_name,
)

DEFAULT_PARQUET = Path("/lg-home/cog8/lwli6/Data/swebench_pro/test-00000-of-00001.parquet")

WORKSPACE_DIRS = (
    "public",
    "restricted",
    "sealed",
    "reference",
    "verifier",
    "run/logs",
)


def read_parquet_row(path: Path, *, instance_id: str | None, row_index: int | None) -> dict:
    try:
        import pyarrow.parquet as parquet
    except ModuleNotFoundError as exc:  # pragma: no cover - environment guard
        raise SystemExit("reading the SWE-Pro parquet requires pyarrow") from exc
    rows = parquet.read_table(path).to_pylist()
    if instance_id is not None:
        matches = [(index, row) for index, row in enumerate(rows) if row.get("instance_id") == instance_id]
        if len(matches) != 1:
            raise SystemExit(f"instance_id matched {len(matches)} rows: {instance_id}")
        index, row = matches[0]
    else:
        index = 0 if row_index is None else row_index
        row = rows[index]
    return {"row_index": index, "source_parquet": str(path.resolve()), "raw": row}


def write_public(workspace: Path, raw: dict, contract: str) -> None:
    public = workspace / "public"
    (public / "problem_statement.md").write_text(str(raw.get("problem_statement") or ""), encoding="utf-8")
    (public / "interface_contract.md").write_text(contract, encoding="utf-8")


def write_restricted(workspace: Path, raw: dict, parsed: dict, meta: dict) -> None:
    restricted = workspace / "restricted"
    (restricted / "original_test.patch").write_text(str(raw.get("test_patch") or ""), encoding="utf-8")
    (restricted / "test_seeds.json").write_text(
        json.dumps(
            {
                "fail_to_pass_source": parsed["fail_to_pass"],
                "pass_to_pass_source": parsed["pass_to_pass"],
                "selected_test_files_to_run": parsed["selected_test_files_to_run"],
                "note": (
                    "f2p here is the SOURCE dataset's fail-to-pass list, provided only as a "
                    "candidate seed. The converted verifier's f2p is recomputed from the "
                    "base/gold replay by the Controller, not copied from this file. p2p is "
                    "inherited from pass_to_pass and its liveness is verified in the replay."
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    # The dataset's own command is evidence about how the base tree is built, so
    # the builder may see it; it contains no reference-solution content.
    (restricted / "base_state.json").write_text(
        json.dumps(
            {
                "base_commit": meta["base_commit"],
                "before_repo_set_cmd": meta["before_repo_set_cmd"],
                "checkout_commit": meta["checkout_commit"],
                "pr_commit": meta["pr_commit"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def write_sealed(workspace: Path, raw: dict) -> None:
    sealed = workspace / "sealed"
    (sealed / "gold.patch").write_text(str(raw.get("patch") or ""), encoding="utf-8")
    (sealed / "requirements.md").write_text(str(raw.get("requirements") or ""), encoding="utf-8")
    (sealed / "interface.md").write_text(str(raw.get("interface") or ""), encoding="utf-8")
    (sealed / "README.md").write_text(
        "# Sealed construction evidence — Converter only\n\n"
        "The Converter may read this directory. Solver and QA candidate roles may not. It holds:\n\n"
        "- `gold.patch`: the reference solution. Applied only by deterministic\n"
        "  scripts during replay and inspected by Converter only as one known-correct\n"
        "  implementation; never use it as a similarity target or normative source.\n"
        "- `requirements.md`: derived from the reference patch; it names private\n"
        "  helpers the patch introduced and prescribes implementation paths.\n"
        "- `interface.md`: the raw interface field, including `Path:` lines that\n"
        "  reveal which files the reference solution touched. The solver-visible\n"
        "  subset lives in `public/interface_contract.md`.\n",
        encoding="utf-8",
    )


def materialize_repo(
    workspace: Path, meta: dict, *, image: str, timeout: int = 1800, local_root: Path | None = None,
) -> dict:
    """Check out the repo in its dataset-defined base state.

    Two performance facts drive the implementation:

    * the workspace lives on NFS, where creating ~50k files takes minutes and can
      blow any sane timeout, while local disk does the same work in seconds;
    * ``node_modules``/``.git`` are the bulk of a JS repo (547 MB + 104 MB of
      NodeBB's 719 MB) and the container image already has dependencies
      installed, so an agent reading source does not need them.

    So the tree is extracted with tar (one streaming write rather than one
    syscall per file) into a local staging directory, then linked into the
    workspace. Files are chowned back to the invoking user so the host can manage
    them without root.
    """
    public_repo = workspace / "public" / "repo"
    attempt_root = workspace.parent if workspace.name == ".compat" else workspace
    prepared_repo = attempt_root / "prepare" / "repo"
    staging = (local_root or Path("/tmp/vc_scratch/repos")) / safe_name(meta["instance_id"])
    staging.parent.mkdir(parents=True, exist_ok=True)
    if public_repo.is_symlink() or public_repo.exists():
        if public_repo.is_symlink():
            public_repo.unlink()
        elif public_repo.is_dir() and not any(public_repo.iterdir()):
            public_repo.rmdir()
    public_repo.parent.mkdir(parents=True, exist_ok=True)
    prepared_repo.parent.mkdir(parents=True, exist_ok=True)
    if prepared_repo.is_symlink():
        prepared_repo.unlink()
    staging.mkdir(parents=True, exist_ok=True)
    script = r'''
set -uo pipefail
cd /app
eval "$BASE_STATE_CMD"
base_state_rc=$?
echo "__BASE_STATE_RC=$base_state_rc"
git rev-parse HEAD
git status --porcelain | head -50
rm -rf /staging/repo
mkdir -p /staging/repo
tar cf - --exclude=./node_modules --exclude=./.git . | (cd /staging/repo && tar xf -)
echo "__COPIED_FILES=$(find /staging/repo -type f | wc -l)"
echo "__COPIED_SIZE=$(du -sh /staging/repo | cut -f1)"
chown -R "$HOST_UID:$HOST_GID" /staging/repo
'''
    command = [
        "docker", "run", "--rm", "--network", "none", "--entrypoint", "/bin/bash",
        "-v", f"{staging.resolve()}:/staging",
        "-e", f"BASE_STATE_CMD={build_base_state_script(meta['base_commit'], meta['before_repo_set_cmd'])}",
        "-e", f"HOST_UID={os.getuid()}", "-e", f"HOST_GID={os.getgid()}",
        image, "-c", script,
    ]
    log_dir = workspace / "run" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=timeout, check=False,
        )
        output, returncode = result.stdout, result.returncode
    except subprocess.TimeoutExpired as exc:
        raw = exc.stdout or ""
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        output, returncode = raw + "\nTIMEOUT\n", None
    (log_dir / "prepare_repo.log").write_text(output, encoding="utf-8")

    observed_head = None
    for line in output.splitlines():
        token = line.strip()
        if len(token) == 40 and all(c in "0123456789abcdef" for c in token):
            observed_head = token
            break

    repo_dir = staging / "repo"
    linked = False
    if repo_dir.is_dir():
        prepared_repo.symlink_to(repo_dir)
        public_repo.symlink_to(prepared_repo)
        linked = True
    return {
        "returncode": returncode,
        "log": str((log_dir / "prepare_repo.log").resolve()),
        "observed_head": observed_head,
        # A base state that is not the declared commit invalidates every
        # downstream replay result, so it is checked rather than assumed.
        "head_matches_base": observed_head == meta["base_commit"] if observed_head else None,
        "staging": str(repo_dir),
        "prepared_repo": str(prepared_repo),
        "linked_into_workspace": linked,
        "copied_files": _marker(output, "COPIED_FILES"),
        "copied_size": (re.search(r"^__COPIED_SIZE=(\S+)$", output, re.MULTILINE) or [None, None])[1],
    }


def _marker(output: str, name: str) -> int | None:
    match = re.search(rf"^__{name}=(\d+)$", output, re.MULTILINE)
    return int(match.group(1)) if match else None


def _test_patch_targets(test_patch: str) -> set[str]:
    """Files the historical test patch touches.

    Needed because some languages (Go in particular) report test ids as bare
    function names — ``TestState`` — with no file path at all, so the f2p/p2p
    lists alone cannot say which files to snapshot. The patch header can.
    """
    targets: set[str] = set()
    for match in re.finditer(r"^\+\+\+ b/(\S+)", str(test_patch or ""), re.MULTILINE):
        target = match.group(1).strip()
        if target and target != "/dev/null":
            targets.add(target)
    for match in re.finditer(r"^diff --git a/\S+ b/(\S+)", str(test_patch or ""), re.MULTILINE):
        targets.add(match.group(1).strip())
    return targets


def copy_original_tests(workspace: Path, parsed: dict, test_patch: str = "") -> int:
    """Snapshot the test files the source task touches, for the builder to read.

    Three sources, because no single one covers every language: the dataset's
    ``selected_test_files_to_run``, the file part of each f2p/p2p node id, and
    the files named by the historical test patch itself.
    """
    target = workspace / "restricted" / "original_tests"
    target.mkdir(parents=True, exist_ok=True)
    repo = workspace / "public" / "repo"
    wanted: set[str] = {
        resolve_repo_test_path(repo, path)
        for path in parsed["selected_test_files_to_run"]
    }
    for node in parsed["fail_to_pass"] + parsed["pass_to_pass"]:
        head = normalize_node_id(node).split("::", 1)[0].split("|", 1)[0].strip()
        # A bare symbol name (Go's `TestState`) is not a path; skip it and rely
        # on the test patch's file list instead.
        if head and ("/" in head or head.endswith((".py", ".js", ".ts", ".go", ".rs"))):
            wanted.add(resolve_repo_test_path(repo, head))
    wanted |= _test_patch_targets(test_patch)
    copied = 0
    for relative in sorted(wanted):
        source = repo / relative
        if source.is_file() and not (target / relative).exists():
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            copied += 1
    return copied


def resolve_test_selectors(workspace: Path, parsed: dict, language: str) -> dict:
    """Freeze executable F2P/P2P selectors before any model session.

    Selector resolution is preparation work, not Converter work.  The source
    dataset already supplies selectors for most rows; this step normalizes
    language-specific spellings, checks referenced test files against the
    prepared base tree, preserves unresolved selectors for an explicit replay
    error, and records the exact immutable list consumed by the verifier.
    """
    repo = workspace / "public" / "repo"
    result: dict[str, object] = {
        "language": language,
        "method": "deterministic_dataset_selector_normalization",
        "selected_test_files_to_run": sorted({
            resolve_repo_test_path(repo, path)
            for path in (parsed.get("selected_test_files_to_run") or [])
        }),
    }
    for group in ("fail_to_pass", "pass_to_pass"):
        source = [str(item) for item in parsed[group]]
        resolved: list[str] = []
        missing_files: list[str] = []
        duplicate_ids: list[str] = []
        seen: set[str] = set()
        for raw in source:
            node = normalize_node_id(raw, language)
            file_part, separator, node_part = node.partition("::")
            if separator:
                resolved_file = resolve_repo_test_path(repo, file_part)
                node = f"{resolved_file}::{node_part}"
            if node in seen:
                duplicate_ids.append(node)
                continue
            seen.add(node)
            resolved.append(node)
            test_file = node.split("::", 1)[0].split("|", 1)[0].strip()
            if test_file and ("/" in test_file or test_file.endswith((".py", ".js", ".ts", ".go", ".rs"))):
                if not (repo / test_file).is_file():
                    missing_files.append(test_file)
        result[group] = {
            "source": source,
            "resolved": resolved,
            "count": len(resolved),
            "duplicate_ids": sorted(set(duplicate_ids)),
            "missing_test_files": sorted(set(missing_files)),
        }
    path = workspace / "restricted" / "resolved_test_selectors.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def _preflight_test_files(workspace: Path, repo: Path, parsed: dict, language: str) -> set[str]:
    """Return concrete files needed by the native preflight command.

    Dataset selector fields are not uniformly file paths: Go rows commonly
    contain bare test function names (for example ``TestLastFM``). Those
    names belong in the selector list, but must not be passed to a file
    existence check or to ``go test`` as if they were paths. The historical
    test patch is the deterministic source for the concrete files in that
    case, and is also useful as a fallback for other selector styles.
    """
    test_files: set[str] = set()
    for path in parsed.get("selected_test_files_to_run") or []:
        normalized = resolve_repo_test_path(repo, path)
        if "/" in normalized or normalized.endswith((".py", ".js", ".ts", ".go", ".rs")):
            test_files.add(normalized)
    for node in parsed.get("fail_to_pass", []) + parsed.get("pass_to_pass", []):
        head = normalize_node_id(str(node), language).split("::", 1)[0].split("|", 1)[0].strip()
        if head and ("/" in head or head.endswith((".py", ".js", ".ts", ".go", ".rs"))):
            test_files.add(resolve_repo_test_path(repo, head))
    patch_path = workspace / "restricted" / "original_test.patch"
    if patch_path.is_file():
        for relative in _test_patch_targets(patch_path.read_text(encoding="utf-8", errors="replace")):
            test_files.add(resolve_repo_test_path(repo, relative))
    return test_files


def run_environment_preflight(
    workspace: Path, meta: dict, parsed: dict, timeout: int = 600,
    selector_resolution: dict[str, Any] | None = None,
    repo_result: dict[str, Any] | None = None,
) -> dict:
    """Run deterministic toolchain/import/collection checks before any model."""
    language = str(meta.get("repo_language") or "").lower()
    repo = workspace / "public" / "repo"
    test_files = _preflight_test_files(workspace, repo, parsed, language)
    execution = discover_execution_spec(repo, meta)
    # Prepare freezes the timeout used by every subsequent deterministic
    # execution stage; callers cannot silently introduce a second contract.
    timeout = int(execution.timeout_seconds)
    missing_files = sorted(path for path in test_files if not (repo / path).is_file())
    checks: dict[str, Any] = {
        "repo_present": repo.is_dir(),
        "test_files_present": not missing_files,
        "selector_validity": not any(
            (selector_resolution or {}).get(group, {}).get(key)
            for group in ("fail_to_pass", "pass_to_pass")
            for key in ("duplicate_ids", "missing_test_files")
        ),
        "base_entrypoint": bool(meta.get("before_repo_set_cmd")) and (
            repo_result is None or repo_result.get("head_matches_base") is not False
        ),
        "docker_command": False,
        "python": None,
        "pytest": None,
        "dependencies_and_project_import": None,
        "test_collection": None,
    }
    result: dict[str, Any] = {
        "schema_version": "1.0", "language": language,
        "test_files": sorted(test_files), "missing_test_files": missing_files,
        "execution_spec": execution.as_dict(),
        "checks": checks, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    if not repo.is_dir() or missing_files:
        result["status"] = "FAIL"
        return result

    if language not in {"python", "python3"}:
        if not execution.supported:
            checks["dependencies_and_project_import"] = False
            checks["test_collection"] = False
            result["failure_class"] = "INFRASTRUCTURE"
            result["failure_reason"] = execution.reason
            result["status"] = "FAIL"
            return result
        files = " ".join(shlex.quote(path) for path in sorted(test_files))
        if language in {"javascript", "typescript", "node", "nodejs", "js", "ts"}:
            runner_checks = {
                "mocha": f"node --version && {execution.package_manager} --version && test -x node_modules/.bin/mocha && node_modules/.bin/mocha --dry-run --reporter dot {files}",
                "jest": f"node --version && {execution.package_manager} --version && test -x node_modules/.bin/jest && node_modules/.bin/jest --listTests",
                "vitest": f"node --version && {execution.package_manager} --version && test -x node_modules/.bin/vitest && node_modules/.bin/vitest list",
                # ospec projects commonly compile a native test bundle through
                # test/TestBuilder.js and launch it with test/test.js.  Check
                # that harness and its dependency without running the full
                # suite during Prepare.
                "ospec": "node --version && npm --version && test -f node_modules/ospec/ospec.js && test -f test/test.js && test -f test/TestBuilder.js && node --check test/test.js",
            }
            native_command = runner_checks.get(execution.runner_family, "false")
            script = native_command + "\nrc=$?\necho __PREFLIGHT_NATIVE_RC=$rc\n"
        else:
            script = "go version\ngo_rc=$?\ngo list -buildvcs=false ./...\ncollect_rc=$?\necho __PREFLIGHT_GO_RC=$go_rc\necho __PREFLIGHT_COLLECT_RC=$collect_rc\n"

    execution_cwd = Path(execution.cwd)
    preflight_files = []
    for path in sorted(test_files):
        if str(execution_cwd) != ".":
            try:
                preflight_files.append(str(Path(path).relative_to(execution_cwd)))
                continue
            except ValueError:
                preflight_files.append(os.path.relpath(path, str(execution_cwd)))
                continue
        preflight_files.append(path)
    quoted_files = " ".join(shlex.quote(path) for path in preflight_files)
    if language in {"python", "python3"}:
        script = f'''set +e
python3 --version >/tmp/preflight_python.out 2>&1
python_rc=$?
pytest --version >/tmp/preflight_pytest.out 2>&1
pytest_rc=$?
python3 -c 'import pytest' >/tmp/preflight_import.out 2>&1
import_rc=$?
pytest --collect-only -q {quoted_files} >/tmp/preflight_collect.out 2>&1
collect_rc=$?
cat /tmp/preflight_python.out /tmp/preflight_pytest.out /tmp/preflight_import.out /tmp/preflight_collect.out
echo "__PREFLIGHT_PYTHON_RC=$python_rc"
echo "__PREFLIGHT_PYTEST_RC=$pytest_rc"
echo "__PREFLIGHT_IMPORT_RC=$import_rc"
echo "__PREFLIGHT_COLLECT_RC=$collect_rc"
'''
    else:
        script = "set +e\n" + script
    command = [
        "docker", "run", "--rm", "--network", "none", "--entrypoint", "/bin/bash",
        # Keep image-provided dependencies (notably node_modules) visible at
        # /app.  The prepared source tree is copied over the image checkout
        # from /source instead of bind-mounting an incomplete host tree on top
        # of the runtime environment.
        "-v", f"{repo.resolve()}:/source:ro",
        meta["docker_image"], "-c",
        "cp -a /source/. /app/; cd /app/" + str(execution.cwd) + "; export HOME=/tmp; mkdir -p \"$HOME\"; " + script,
    ]
    log_path = workspace / "run" / "logs" / "environment_preflight.log"
    try:
        proc = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, timeout=timeout, check=False)
        output, returncode = proc.stdout, proc.returncode
    except subprocess.TimeoutExpired as exc:
        raw = exc.stdout or ""
        output = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
        output += "\nTIMEOUT\n"
        returncode = None
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(output, encoding="utf-8")

    def marker(name: str) -> int | None:
        match = re.search(rf"^__PREFLIGHT_{name}=(\d+)$", output, re.MULTILINE)
        return int(match.group(1)) if match else None

    checks["docker_command"] = returncode == 0
    if language in {"python", "python3"}:
        checks["python"] = marker("PYTHON_RC") == 0
        checks["pytest"] = marker("PYTEST_RC") == 0
        checks["dependencies_and_project_import"] = marker("IMPORT_RC") == 0
        checks["test_collection"] = marker("COLLECT_RC") == 0
    elif language in {"javascript", "typescript", "node", "nodejs", "js", "ts"}:
        checks["python"] = "SKIPPED"
        checks["pytest"] = "SKIPPED"
        native_rc = marker("NATIVE_RC")
        checks["dependencies_and_project_import"] = native_rc == 0
        checks["test_collection"] = native_rc == 0
    else:
        checks["python"] = "SKIPPED"
        checks["pytest"] = "SKIPPED"
        checks["dependencies_and_project_import"] = marker("GO_RC") == 0
        checks["test_collection"] = marker("COLLECT_RC") == 0
    essential = [value for key, value in checks.items() if key not in {"python", "pytest"}]
    if language in {"python", "python3"}:
        essential.extend([checks["python"], checks["pytest"]])
    result.update({"status": "PASS" if all(value is True for value in essential) else "FAIL",
                   "returncode": returncode, "log": str(log_path.resolve()),
                   "output_tail": output[-4000:]})
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_PARQUET)
    parser.add_argument("--instance-id")
    parser.add_argument("--row-index", type=int)
    parser.add_argument("--runs-root", type=Path, default=DEFAULT_RUNS_ROOT)
    parser.add_argument("--materialize-repo", action="store_true")
    parser.add_argument(
        "--local-repos-root", type=Path, default=Path("/tmp/vc_scratch/repos"),
        help="local (non-NFS) directory to stage the working tree in; symlinked into public/repo",
    )
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()

    source = read_parquet_row(args.data, instance_id=args.instance_id, row_index=args.row_index)
    raw = source["raw"]
    parsed = {
        "fail_to_pass": as_list(raw.get("fail_to_pass")),
        "pass_to_pass": as_list(raw.get("pass_to_pass")),
        "selected_test_files_to_run": as_list(raw.get("selected_test_files_to_run")),
    }
    id_info = parse_instance_id(raw["instance_id"])
    contract, contract_audit = extract_contract(str(raw.get("interface") or ""), str(raw.get("problem_statement") or ""))

    run_layout = RunLayout.for_instance(args.runs_root, raw["instance_id"])
    attempt = run_layout.allocate_attempt()
    workspace = attempt.runtime
    for relative in WORKSPACE_DIRS:
        (workspace / relative).mkdir(parents=True, exist_ok=True)

    meta = {
        "instance_id": raw["instance_id"],
        "repo": raw["repo"],
        "base_commit": raw["base_commit"],
        "repo_language": raw.get("repo_language", ""),
        "dockerhub_tag": raw["dockerhub_tag"],
        "docker_image": image_ref(raw["dockerhub_tag"]),
        "before_repo_set_cmd": raw.get("before_repo_set_cmd", ""),
        "checkout_commit": checkout_commit(raw.get("before_repo_set_cmd", "")),
        "pr_commit": id_info["pr_commit"],
        "version_commit": id_info["version_commit"],
        "instance_tail_kind": id_info["tail_kind"],
        "issue_specificity": as_list(raw.get("issue_specificity")),
        "issue_categories": as_list(raw.get("issue_categories")),
        "source_parquet": source["source_parquet"],
        "row_index": source["row_index"],
        "counts": {
            "fail_to_pass_source": len(parsed["fail_to_pass"]),
            "pass_to_pass_source": len(parsed["pass_to_pass"]),
            "selected_test_files_to_run": len(parsed["selected_test_files_to_run"]),
        },
        "contract_extraction": contract_audit,
        "prepared_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    source_row_path = attempt.source / "dataset_row.json"
    source_row_value = {"row_index": source["row_index"], "source_parquet": source["source_parquet"], "raw": raw}
    source_row_text = json.dumps(source_row_value, ensure_ascii=False, indent=2) + "\n"
    if source_row_path.is_file() and source_row_path.read_text(encoding="utf-8") != source_row_text:
        raise SystemExit("instance source contract already exists with different dataset row")
    source_row_path.write_text(source_row_text, encoding="utf-8")
    source_metadata = attempt.source / "metadata.json"
    if not source_metadata.is_file():
        source_metadata.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (workspace / "run" / "metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (workspace / "run" / "source_row.json").write_text(
        json.dumps(source, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    write_public(workspace, raw, contract)
    write_restricted(workspace, raw, parsed, meta)
    write_sealed(workspace, raw)
    source_manifest = {
        "schema_version": "1.0",
        "instance_id": meta["instance_id"],
        "row_index": meta["row_index"],
        "source_files": {
            relative: hashlib.sha256((attempt.source / relative).read_bytes()).hexdigest()
            for relative in ("dataset_row.json", "restricted/original_test.patch", "sealed/gold.patch")
            if (attempt.source / relative).is_file()
        },
        "immutable": True,
    }
    (attempt.source / "source_manifest.json").write_text(
        json.dumps(source_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    taxonomy = PROJECT_ROOT / "docs" / "references" / "deepswe_verifier_taxonomy.md"
    if taxonomy.is_file():
        shutil.copy2(taxonomy, workspace / "reference" / taxonomy.name)

    repo_result = None
    if args.materialize_repo:
        repo_result = materialize_repo(
            workspace, meta, image=meta["docker_image"],
            timeout=args.timeout, local_root=args.local_repos_root,
        )
        meta["repo_materialization"] = repo_result
        (workspace / "run" / "metadata.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    execution_spec = discover_execution_spec(workspace / "public" / "repo", meta)
    meta["execution_spec"] = execution_spec.as_dict()
    meta["execution_spec_hash"] = execution_spec_hash(execution_spec)
    (workspace / "run" / "metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    copied_tests = copy_original_tests(workspace, parsed, str(raw.get('test_patch') or ''))
    selector_resolution = resolve_test_selectors(workspace, parsed, meta["repo_language"])
    # Freeze the package-facing P2P asset boundary once, during Prepare.  The
    # package stage consumes this derived view; it must not rediscover assets
    # from the historical patch or verifier tree.
    p2p_resolved = list((selector_resolution.get("pass_to_pass") or {}).get("resolved") or [])
    p2p_files = sorted({str(item).split("::", 1)[0].split("|", 1)[0]
                        for item in p2p_resolved if str(item).strip()})
    p2p_assets = {
        "schema_version": "1.0",
        "resolved_selectors": p2p_resolved,
        "f2p_resolved_selectors": list((selector_resolution.get("fail_to_pass") or {}).get("resolved") or []),
        "required_test_files": p2p_files,
        "required_fixtures": [],
        "shared_support_files": [],
        "ambiguous_items": [],
        "source": "prepare.selector_resolution",
    }
    (workspace / "restricted" / "p2p_assets.json").write_text(
        json.dumps(p2p_assets, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    environment_preflight = run_environment_preflight(
        workspace, meta, parsed, timeout=args.timeout,
        selector_resolution=selector_resolution, repo_result=repo_result,
    )
    (workspace / "run" / "environment_preflight.json").write_text(
        json.dumps(environment_preflight, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    # A directory left in the local staging cache is not proof that this
    # Prepare invocation successfully materialized the declared base.  In
    # particular, a Docker permission failure can leave a symlink pointing at
    # an older cache entry while the command itself returned 126.  Keep the
    # source gate tied to the current Docker result and the observed commit.
    base_repo_materialized = bool(
        repo_result
        and repo_result.get("returncode") == 0
        and repo_result.get("head_matches_base") is True
        and repo_result.get("linked_into_workspace") is True
        and (workspace / "public" / "repo").is_dir()
    )
    preflight = {
        "schema_version": "1.0",
        "status": "PASS",
        "checks": {
            "metadata": (workspace / "run" / "metadata.json").is_file(),
            "problem_statement": (workspace / "public" / "problem_statement.md").stat().st_size > 0,
            "gold_patch": (workspace / "sealed" / "gold.patch").stat().st_size > 0,
            "base_repo_materialized": base_repo_materialized,
            "test_patch": bool(str(raw.get("test_patch") or "").strip()),
            "f2p_files_resolved": not selector_resolution["fail_to_pass"]["missing_test_files"],
            "p2p_files_resolved": not selector_resolution["pass_to_pass"]["missing_test_files"],
            "environment_preflight": environment_preflight["status"] == "PASS",
        },
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    preflight["status"] = "PASS" if all(preflight["checks"].values()) else "FAIL"
    (workspace / "run" / "source_preflight.json").write_text(
        json.dumps(preflight, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(json.dumps(
        {
            "run_root": str(run_layout.root),
            "attempt": str(attempt.root),
            "workspace": str(workspace),
            "instance_id": meta["instance_id"],
            "repo": meta["repo"],
            "language": meta["repo_language"],
            "pr_commit": meta["pr_commit"],
            "tail_kind": meta["instance_tail_kind"],
            "checkout_commit_matches_pr": meta["checkout_commit"] == meta["pr_commit"],
            "contract_mode": contract_audit["mode"],
            "copied_test_files": copied_tests,
            "selector_resolution": selector_resolution,
            "source_preflight": preflight,
            "environment_preflight": environment_preflight,
            "repo_materialization": repo_result,
        },
        ensure_ascii=False, indent=2,
    ))
    return 0 if preflight["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
