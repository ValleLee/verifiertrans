import json
import os
import subprocess
from pathlib import Path

from verifier_trans.deterministic.packaging.package_task import GRADER


def test_generated_grader_uses_node_whitelist_and_partial_reward(tmp_path: Path) -> None:
    tests = tmp_path / "tests"
    logs = tmp_path / "logs"
    tests.mkdir()
    logs.mkdir()
    report = logs / "report.json"
    report.write_text(
        json.dumps(
            {
                "results": {
                    "tests": [
                        {"suite": ["suite"], "name": "f2p_ok", "status": "passed"},
                        {"suite": ["suite"], "name": "p2p_ok", "status": "passed"},
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    (tests / "config.json").write_text(
        json.dumps(
            {
                "f2p_node_ids": ["suite.f2p_ok", "suite.f2p_missing"],
                "p2p_node_ids": ["suite.p2p_ok"],
                "grade": {
                    "format": "ctrf",
                    "node_id": "suite.name",
                    "tool_label": "functional-verifier",
                    "reports": [str(report)],
                },
            }
        ),
        encoding="utf-8",
    )
    grader = tests / "grader.py"
    grader.write_text(GRADER, encoding="utf-8")
    env = {**os.environ, "TESTS_DIR": str(tests), "VERIFIER_DIR": str(logs)}
    result = subprocess.run(
        ["python3", str(grader), "grade"], env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    reward = json.loads((logs / "reward.json").read_text(encoding="utf-8"))
    assert reward == {
        "reward": 0,
        "f2p_total": 2,
        "f2p_passed": 1,
        "p2p_total": 1,
        "p2p_passed": 1,
        "f2p": 0.5,
        "p2p": 1.0,
        "partial": 2 / 3,
    }


def test_generated_grader_patch_paths_preserves_diff_order(tmp_path: Path) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    grader = tests / "grader.py"
    grader.write_text(GRADER, encoding="utf-8")
    patch = tmp_path / "change.patch"
    patch.write_text(
        "diff --git a/z.txt b/z.txt\n--- a/z.txt\n+++ b/z.txt\n"
        "diff --git a/a.txt b/a.txt\n--- a/a.txt\n+++ b/a.txt\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["python3", str(grader), "patch-paths", str(patch)],
        capture_output=True,
        text=True,
    )
    assert result.stdout.splitlines() == ["z.txt", "a.txt"]
