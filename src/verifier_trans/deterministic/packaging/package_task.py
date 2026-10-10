#!/usr/bin/env python3
"""Package an accepted conversion as a DeepSWE-compatible task directory.

The output mirrors the layout of a real DeepSWE bundle (see
``Data/deepswe/tasks/<id>/``) so a converted task can be dropped into that
evaluation flow: ``task.toml``, ``instruction.md``, ``environment/Dockerfile``,
``tests/{config.json,grader.py,test.sh,test.patch,Dockerfile}`` and
``solution/solution.patch``.

Two things are deliberately *not* copied into the task: the intermediate
construction directory (spec, audit, replay logs) and the reference solution's
role beyond a held-out `solution.patch` for offline review, which grading never
executes.
"""
from __future__ import annotations

import argparse
import difflib
import json
import shutil
from pathlib import Path

from ..execution.base import package_execution_plan, _manifest_functional_file
from ..execution.services import service_bootstrap_script
from .test_patch import retain_p2p_test_patch
from ...paths import attempt_from_path


def manifest_source_ids(value: object) -> list[str]:
    """Read source ids from either supported coverage representation."""
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, dict):
        nested = value.get("source_test_ids")
        if isinstance(nested, list):
            return [str(item) for item in nested if str(item).strip()]
        return [str(item) for item in value if str(item).strip()]
    return []

GRADER = r'''#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

APP = Path(os.environ.get("APP_DIR", "/app"))
TESTS = Path(os.environ.get("TESTS_DIR", "/tests"))
LOGS = Path(os.environ.get("VERIFIER_DIR", "/logs/verifier"))
ARTIFACTS = Path(os.environ.get("ARTIFACTS_DIR", "/logs/artifacts"))
TEST_PATCH = TESTS / "test.patch"
MODEL_PATCH = ARTIFACTS / "model.patch"
RANK = {"passed": 0, "skipped": 1, "failed": 2}


def load_config():
    return json.loads((TESTS / "config.json").read_text(encoding="utf-8"))


def patch_paths(text):
    """Return unique touched paths in unified-diff order."""
    seen, paths = set(), []
    for line in text.splitlines():
        path = None
        match = re.match(r'^diff --git ["\']?a/(.*?)["\']? ["\']?b/(.*?)["\']?$', line)
        if match:
            path = match.group(2)
        elif line.startswith("+++ b/"):
            path = line[6:].strip()
        elif line.startswith("--- a/"):
            path = line[6:].strip()
        if path and path != "/dev/null" and path not in seen:
            seen.add(path)
            paths.append(path)
    return paths


def read_patch(path):
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def git(*args, **kwargs):
    return subprocess.run(["git", *args], cwd=APP, **kwargs)


def reset_paths(paths, ref):
    for path in paths:
        result = git("checkout", "-q", ref, "--", path, stderr=subprocess.DEVNULL)
        if result.returncode and ref == "HEAD" and (APP / path).exists():
            subprocess.run(["rm", "-rf", "--", path], cwd=APP, check=False)


def prepare():
    LOGS.mkdir(parents=True, exist_ok=True)
    APP.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "config", "--global", "--add", "safe.directory", str(APP)], check=False)
    config = load_config()
    model_text = read_patch(MODEL_PATCH)
    if model_text:
        reset_paths(patch_paths(model_text), config["base_commit"])
        result = git("apply", "--whitespace=nowarn", str(MODEL_PATCH))
        if result.returncode:
            grade_from_status(config, f2p_ok=False, p2p_ok=False, apply_failed=True)
            return
    test_text = read_patch(TEST_PATCH)
    if test_text:
        reset_paths(patch_paths(test_text), "HEAD")
        result = git("apply", "--whitespace=nowarn", "--allow-empty", str(TEST_PATCH))
        if result.returncode:
            raise SystemExit(result.returncode)


def normalize_status(value):
    value = str(value or "").strip().lower()
    if value == "passed":
        return "passed"
    if value in {"skipped", "pending", "other"}:
        return "skipped"
    return "failed"


def add_status(result, node_id, status, message=""):
    current = result.get(node_id)
    if current is None or RANK[status] > RANK[current[0]]:
        result[node_id] = (status, message if status != "passed" else "")
    elif current[0] != "passed" and not current[1] and message:
        result[node_id] = (current[0], message)


def parse_ctrf(path, cfg):
    result = {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return result
    tests = (doc.get("results") or {}).get("tests") or []
    for item in tests if isinstance(tests, list) else []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        suite = item.get("suite")
        if isinstance(suite, list):
            suite = str(suite[0]).strip() if suite else ""
        else:
            suite = str(suite or "").strip()
        node_id = f"{suite}.{name}" if cfg.get("grade", {}).get("node_id") == "suite.name" and suite else name
        add_status(result, node_id, normalize_status(item.get("status")), str(item.get("message") or item.get("trace") or ""))
    return result


def parse_junit(path):
    result = {}
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return result
    for item in root.iter():
        if item.tag.rsplit("}", 1)[-1] != "testcase":
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        classname = str(item.get("classname") or "").strip()
        node_id = f"{classname}.{name}" if classname else name
        status, message = "passed", ""
        for child in item:
            tag = child.tag.rsplit("}", 1)[-1]
            if tag in {"failure", "error"}:
                status = "failed"
                message = str(child.get("message") or child.text or "").strip()
                break
            if tag == "skipped":
                status = "skipped"
        add_status(result, node_id, status, message)
    return result


def report_statuses(config, report_paths):
    fmt = str(config.get("grade", {}).get("format") or "ctrf").lower()
    merged = {}
    for raw_path in report_paths:
        path = Path(raw_path)
        if not path.is_absolute():
            path = TESTS / path
        parsed = parse_junit(path) if fmt == "junit" else parse_ctrf(path, config)
        for node_id, value in parsed.items():
            add_status(merged, node_id, value[0], value[1])
    return merged


def write_grade(config, statuses, apply_failed=False):
    f2p_ids = [str(item).strip() for item in config.get("f2p_node_ids", []) if str(item).strip()]
    p2p_ids = [str(item).strip() for item in config.get("p2p_node_ids", []) if str(item).strip()]
    f2p_passed = sum(statuses.get(node, ("failed", ""))[0] == "passed" for node in f2p_ids)
    p2p_passed = sum(statuses.get(node, ("failed", ""))[0] == "passed" for node in p2p_ids)
    f2p_total, p2p_total = len(f2p_ids), len(p2p_ids)
    reward = int(f2p_total > 0 and f2p_passed == f2p_total and p2p_passed == p2p_total)
    denominator = f2p_total + p2p_total
    reward_doc = {
        "reward": reward, "f2p_total": f2p_total, "f2p_passed": f2p_passed,
        "p2p_total": p2p_total, "p2p_passed": p2p_passed,
        "f2p": f2p_passed / f2p_total if f2p_total else 0.0,
        "p2p": p2p_passed / p2p_total if p2p_total else 1.0,
        "partial": (f2p_passed + p2p_passed) / denominator if denominator else 0.0,
    }
    if apply_failed:
        reward_doc["apply_failed"] = 1
    LOGS.mkdir(parents=True, exist_ok=True)
    (LOGS / "reward.json").write_text(json.dumps(reward_doc, indent=2) + "\n", encoding="utf-8")
    all_ids = [(node, "f2p") for node in f2p_ids] + [(node, "p2p") for node in p2p_ids]
    tests = [{"name": node, "suite": [bucket], "status": statuses.get(node, ("failed", ""))[0], "message": statuses.get(node, ("failed", ""))[1]} for node, bucket in all_ids]
    summary = {"tests": len(tests), "passed": sum(item["status"] == "passed" for item in tests), "failed": sum(item["status"] == "failed" for item in tests), "skipped": sum(item["status"] == "skipped" for item in tests), "pending": 0, "other": 0}
    ctrf = {"reportFormat": "CTRF", "specVersion": "1.0.0", "results": {"tool": {"name": config.get("grade", {}).get("tool_label", "functional-verifier")}, "summary": summary, "tests": tests}}
    (LOGS / "ctrf.json").write_text(json.dumps(ctrf, indent=2) + "\n", encoding="utf-8")


def grade_from_status(config, f2p_ok, p2p_ok, apply_failed=False):
    f2p_ids = [str(item).strip() for item in config.get("f2p_node_ids", []) if str(item).strip()]
    p2p_ids = [str(item).strip() for item in config.get("p2p_node_ids", []) if str(item).strip()]
    statuses = {node: ("passed" if f2p_ok else "failed", "") for node in f2p_ids}
    statuses.update({node: ("passed" if p2p_ok else "failed", "") for node in p2p_ids})
    write_grade(config, statuses, apply_failed=apply_failed)


def grade(argv):
    config = load_config()
    apply_failed = False
    args = list(argv)
    if args and args[0] == "--apply-failed":
        apply_failed, args = True, args[1:]
    if len(args) == 2 and all(re.fullmatch(r"-?\d+", item) for item in args):
        grade_from_status(config, int(args[0]) == 0, int(args[1]) == 0, apply_failed)
        return
    reports = args or list(config.get("grade", {}).get("reports") or [])
    write_grade(config, report_statuses(config, reports), apply_failed=apply_failed)


if __name__ == "__main__":
    if sys.argv[1:] == ["prepare"]:
        prepare()
    elif sys.argv[1:2] == ["grade"]:
        grade(sys.argv[2:])
    elif len(sys.argv) == 3 and sys.argv[1] == "patch-paths":
        print("\n".join(patch_paths(Path(sys.argv[2]).read_text(encoding="utf-8", errors="replace"))) )
    else:
        raise SystemExit("usage: grader.py prepare | grade [--apply-failed] [REPORT ...] | patch-paths PATCH")
'''


def make_test_sh(f2p_command: str, p2p_command: str, service_bootstrap: str = ":") -> str:
    return f'''#!/bin/bash
set -uo pipefail
trap 'if [ ! -f /logs/verifier/reward.json ]; then mkdir -p /logs/verifier; echo -1 > /logs/verifier/reward.txt; fi' EXIT
cd /app || exit 6
python3 /tests/grader.py prepare || exit $?
[ -f /logs/verifier/reward.json ] && exit 0
mkdir -p /logs/verifier
{service_bootstrap}
set +e
{f2p_command} > /logs/verifier/f2p.log 2>&1
f2p_rc=$?
{p2p_command} > /logs/verifier/p2p.log 2>&1
p2p_rc=$?
set -e
cat /logs/verifier/f2p.log /logs/verifier/p2p.log
python3 /tests/grader.py grade "$f2p_rc" "$p2p_rc"
'''


def toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def add_file_patch(relative_path: str, content: str) -> str:
    lines = content.splitlines(keepends=True)
    if content and (not lines or not lines[-1].endswith("\n")):
        lines[-1] += "\n"
    body = "".join(difflib.unified_diff([], lines, fromfile="/dev/null", tofile=f"b/{relative_path}", n=3))
    return f"diff --git a/{relative_path} b/{relative_path}\nnew file mode 100644\n{body}"


def file_patch(base_root: Path, relative_path: str, content: str) -> str:
    baseline = base_root / relative_path
    if not baseline.is_file():
        return add_file_patch(relative_path, content)
    old_lines = baseline.read_text(encoding="utf-8").splitlines(keepends=True)
    new_lines = content.splitlines(keepends=True)
    if content and (not new_lines or not new_lines[-1].endswith("\n")):
        new_lines[-1] += "\n"
    body = "".join(difflib.unified_diff(
        old_lines, new_lines, fromfile=f"a/{relative_path}", tofile=f"b/{relative_path}", n=3
    ))
    return f"diff --git a/{relative_path} b/{relative_path}\n{body}"


def verifier_files(root: Path) -> tuple[list[tuple[str, str]], dict]:
    manifest_path = root / "verifier" / "manifest.json"
    if not manifest_path.is_file():
        raise SystemExit(f"missing verifier manifest: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid verifier manifest: {exc}") from exc
    for key in ("f2p_command", "p2p_command"):
        if not str(manifest.get(key) or "").strip():
            raise SystemExit(f"verifier manifest must declare a non-empty {key}")
    declared = manifest.get("test_files")
    if not isinstance(declared, list) or not declared:
        raise SystemExit("verifier manifest must declare a non-empty test_files list")
    files: list[tuple[str, str]] = []
    seen: set[str] = set()
    for item in declared:
        if not isinstance(item, dict):
            raise SystemExit("verifier manifest test_files entries must be objects")
        source = str(item.get("source") or "")
        target = str(item.get("target") or "")
        if not source or Path(source).is_absolute() or ".." in Path(source).parts:
            raise SystemExit(f"invalid verifier source path: {source!r}")
        if not target or Path(target).is_absolute() or ".." in Path(target).parts:
            raise SystemExit(f"invalid verifier target path: {target!r}")
        if target in seen:
            raise SystemExit(f"duplicate verifier target path: {target}")
        seen.add(target)
        if not (root / "verifier" / source).is_file():
            raise SystemExit(f"verifier manifest source does not exist: {source}")
        files.append((source, target))
    functional_name = _manifest_functional_file(root / "verifier")
    if not functional_name or functional_name not in {source for source, _ in files}:
        raise SystemExit("verifier manifest must declare functional_artifact in test_files")
    return files, manifest


def build_instruction(root: Path) -> str:
    """Use the Converter's final F2P-supported scope as solver instruction."""
    path = root / "verifier" / "instruction_scope.md"
    if not path.is_file():
        raise SystemExit(f"missing final instruction scope: {path}")
    text = path.read_text(encoding="utf-8").strip()
    if not text.endswith("INSTRUCTION_SCOPE: PASS"):
        raise SystemExit("instruction_scope.md is missing the INSTRUCTION_SCOPE: PASS marker")
    return text + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--published-image", help="sanitized image tag; defaults to the source image")
    parser.add_argument("--force", action="store_true", help="package even if the gate/audit did not pass")
    args = parser.parse_args()
    root = args.workspace.resolve()

    check_path = root / "run" / "check.json"
    if not check_path.is_file():
        raise SystemExit("refusing to package: no replay evidence at run/check.json")
    check = json.loads(check_path.read_text(encoding="utf-8"))
    qa_path = root / "run" / "qa.json"
    qa = json.loads(qa_path.read_text(encoding="utf-8")) if qa_path.is_file() else {}
    final_path = root / "run" / "final.json"
    final = json.loads(final_path.read_text(encoding="utf-8")) if final_path.is_file() else {}
    audit_path = root / "run" / "audit" / "audit.md"
    audit_lines = [line.strip() for line in audit_path.read_text(encoding="utf-8").splitlines() if line.strip()] if audit_path.is_file() else []
    audit_verdict = "MISSING"
    for line in reversed(audit_lines):
        upper = line.upper()
        if upper in {"PASS", "NEED_REPAIR"}:
            audit_verdict = upper
            break
        if ":" in upper and upper.split(":", 1)[1].strip() in {"PASS", "NEED_REPAIR"}:
            audit_verdict = upper.split(":", 1)[1].strip()
            break
    new_pipeline_ok = final.get("accepted") is True
    old_pipeline_ok = audit_verdict == "PASS" and qa.get("accepted") is True
    if not args.force and (not check.get("accepted") or not (new_pipeline_ok or old_pipeline_ok)):
        raise SystemExit(
            f"refusing to package: replay={check.get('accepted')} audit={audit_verdict} "
            f"qa={qa.get('accepted')} final={final.get('accepted')} "
            "(pass --force to package for inspection only)"
        )

    meta = json.loads((root / "run" / "metadata.json").read_text(encoding="utf-8"))
    if not isinstance(meta.get("execution_spec"), dict):
        raise SystemExit("refusing to package: missing Prepare execution_spec")
    attempt = attempt_from_path(root)
    task = attempt.packaging / "candidate_task"
    if task.exists():
        shutil.rmtree(task)
    for directory in ("environment", "tests", "solution"):
        (task / directory).mkdir(parents=True, exist_ok=True)

    (task / "instruction.md").write_text(build_instruction(root), encoding="utf-8")
    files, manifest = verifier_files(root)
    parts = [file_patch(root / "public" / "repo", target, (root / "verifier" / source).read_text(encoding="utf-8")) for source, target in files]
    original_test_patch = root / "restricted" / "original_test.patch"
    if not original_test_patch.is_file():
        raise SystemExit(f"missing source test patch: {original_test_patch}")
    # The replay runner restores the post-PR test files on top of the base
    # checkout.  The published package must reproduce that same state before
    # running retained P2P regression tests.
    selector_path = root / "restricted" / "resolved_test_selectors.json"
    assets_path = root / "restricted" / "p2p_assets.json"
    if not assets_path.is_file():
        raise SystemExit("refusing to package: missing Prepare p2p_assets.json")
    assets = json.loads(assets_path.read_text(encoding="utf-8"))
    if not isinstance(assets, dict) or assets.get("schema_version") != "1.0":
        raise SystemExit("refusing to package: invalid p2p_assets.json")
    selectors = {
        "pass_to_pass": {"resolved": list(assets.get("resolved_selectors") or [])},
        "fail_to_pass": {"resolved": list(assets.get("f2p_resolved_selectors") or [])},
        "selected_test_files_to_run": list(assets.get("required_test_files") or []),
    }
    retained_test_patch, patch_accounting = retain_p2p_test_patch(
        original_test_patch.read_text(encoding="utf-8"), selectors, root / "public" / "repo"
    )
    test_patch = retained_test_patch + "\n" + "".join(parts)
    (task / "tests" / "test.patch").write_text(test_patch, encoding="utf-8")
    package_report = {
        "schema_version": "1.0", "test_patch_accounting": patch_accounting,
        "p2p_assets": assets,
        "p2p_present": bool(assets.get("resolved_selectors")),
        "p2p_policy": "retained" if assets.get("resolved_selectors") else "source_empty_noop",
        "ambiguities": list(assets.get("ambiguous_items") or []) + list(patch_accounting.get("ambiguous_shared_hunks") or []),
        "execution_spec_hash": meta.get("execution_spec_hash"),
    }
    report_text = json.dumps(package_report, ensure_ascii=False, indent=2) + "\n"
    (task / "tests" / "package_report.json").write_text(report_text, encoding="utf-8")
    (attempt.packaging / "package_report.json").write_text(report_text, encoding="utf-8")
    shutil.copy2(root / "sealed" / "gold.patch", task / "solution" / "solution.patch")

    image = args.published_image or meta["docker_image"]
    task_id = str(meta["instance_id"]).removeprefix("instance_")[:120]
    node_diff = check.get("node_diff") or {}
    f2p_ids = list(manifest.get("f2p_node_ids") or manifest_source_ids(
        manifest.get("source_f2p_coverage")
    ))
    p2p_ids = list(manifest.get("p2p_node_ids") or manifest_source_ids(
        manifest.get("source_p2p_coverage")
    ))
    frozen_environment = (meta.get("execution_spec") or {}).get("environment") or []
    environment_lines = []
    for item in frozen_environment:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            key, value = str(item[0]), str(item[1])
            if key and key.replace("_", "").isalnum() and not key[0].isdigit():
                environment_lines.append(f"{key} = {toml_string(value)}")
    environment_toml = "\n".join(environment_lines)
    task_toml = f'''schema_version = "1.3"
artifacts = ["/logs/artifacts/model.patch"]

[task]
name = {toml_string('local/' + task_id)}
description = "SWE-Pro task with a converted functional verifier"
authors = []
keywords = ["swe-bench-pro", "functional-verifier"]

[metadata]
task_id = {toml_string(task_id)}
display_title = "Converted SWE-Pro functional task"
display_description = "Functional verifier converted from SWE-Pro source evidence."
source_dataset = "SWE-bench Pro"
source_instance_id = {toml_string(meta['instance_id'])}
source_row_index = {int(meta.get('row_index') or 0)}
language = {toml_string(meta.get('repo_language') or '')}
repository_url = {toml_string('https://github.com/' + meta['repo'])}
base_commit_hash = {toml_string(meta['base_commit'])}

[verifier]
network_mode = "no-network"
environment_mode = "separate"
timeout_sec = 1800.0

[verifier.env]
[verifier.environment]
build_timeout_sec = 1800.0
cpus = 2
memory_mb = 8192
storage_mb = 20480

[[verifier.collect]]
command = {toml_string('cd /app && mkdir -p /logs/artifacts && git config --global --add safe.directory /app && git diff --binary ' + meta['base_commit'] + ' HEAD > /logs/artifacts/model.patch')}
timeout_sec = 300.0

[agent]
network_mode = "no-network"
timeout_sec = 10800.0

[environment]
build_timeout_sec = 1800.0
docker_image = {toml_string(image)}
os = "linux"
cpus = 2
memory_mb = 8192
storage_mb = 20480
gpus = 0
mcp_servers = []

[environment.env]
{environment_toml}
[solution.env]
'''
    (task / "task.toml").write_text(task_toml, encoding="utf-8")

    dockerfile = f'''FROM {meta['docker_image']}
ARG BASE_SHA={meta['base_commit']}
RUN cd /app \\
 && git checkout -B deepswe-base "$BASE_SHA" \\
 && (git remote remove origin 2>/dev/null || true) \\
 && git for-each-ref --format='%(refname)' refs/heads refs/tags | grep -v '^refs/heads/deepswe-base$' | xargs -r -n1 git update-ref -d \\
 && git reflog expire --expire=now --all \\
 && git gc --prune=now
WORKDIR /app
CMD ["/bin/bash"]
'''
    (task / "environment" / "Dockerfile").write_text(dockerfile, encoding="utf-8")
    (task / "tests" / "Dockerfile").write_text(f"FROM {image}\n", encoding="utf-8")

    config = {
        "base_commit": meta["base_commit"],
        "f2p_node_ids": f2p_ids or ["converted.functional_f2p"],
        "p2p_node_ids": p2p_ids,
        "p2p_present": bool(p2p_ids),
        "p2p_policy": "retained" if p2p_ids else "source_empty_noop",
        "grade": {"format": "ctrf", "node_id": "name", "tool_label": "functional-verifier", "reports": ["/logs/verifier/ctrf.json"]},
        "source": {
            "dataset": "SWE-bench Pro",
            "instance_id": meta["instance_id"],
            "contract_extraction_mode": (meta.get("contract_extraction") or {}).get("mode"),
        },
        "replay": {
            "accepted": check.get("accepted"),
            "observed_f2p": node_diff.get("f2p", []),
            "inherited_p2p_present": len(node_diff.get("p2p_present", [])),
            "inherited_p2p_missing": node_diff.get("p2p_missing", []),
            "inherited_p2p_regressed": node_diff.get("p2p_regressed", []),
        },
    }
    (task / "tests" / "config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (task / "tests" / "grader.py").write_text(GRADER, encoding="utf-8")
    functional_name = _manifest_functional_file(root / "verifier")
    if not functional_name:
        raise SystemExit("verifier manifest must declare an existing functional_artifact")
    functional_target = next((target for source, target in files if source == functional_name), None)
    package_plan = package_execution_plan(meta, functional_name, functional_target)
    if package_plan is not None:
        package_f2p = package_plan.functional_command
        package_p2p = package_plan.selector_command
        shutil.copy2(package_plan.runner_source, task / "tests" / package_plan.runner_name)
    else:
        raise SystemExit("refusing to package: ExecutionSpec has no supported package adapter")
    (task / "tests" / "resolved_test_selectors.json").write_text(
        json.dumps({"pass_to_pass": selectors["pass_to_pass"]}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (task / "tests" / "test.sh").write_text(
        make_test_sh(package_f2p, package_p2p, service_bootstrap_script(package_plan.spec)),
        encoding="utf-8",
    )
    solve = "#!/bin/bash\nset -euo pipefail\ncd /app\ngit apply /solution/solution.patch\n"
    (task / "solution" / "solve.sh").write_text(solve, encoding="utf-8")
    for path in (task / "tests" / "test.sh", task / "tests" / "grader.py", task / "solution" / "solve.sh"):
        path.chmod(path.stat().st_mode | 0o111)

    print(json.dumps({
        "task": str(task), "source_image": meta["docker_image"], "published_image": image,
        "audit_verdict": audit_verdict, "replay_accepted": check.get("accepted"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
