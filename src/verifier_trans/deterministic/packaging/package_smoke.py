#!/usr/bin/env python3
"""Run a packaged task once with the Gold patch as a smoke test."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from ..preparation.common import build_base_state_script
from ..execution.discovery import ExecutionSpec
from ...paths import attempt_from_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()
    root = args.workspace.resolve()
    attempt = attempt_from_path(root)
    task = attempt.packaging / "candidate_task"
    meta = json.loads((root / "run/metadata.json").read_text(encoding="utf-8"))
    if not isinstance(meta.get("execution_spec"), dict):
        result = {"status": "FAIL", "failure_domain": "package", "errors": ["missing:execution_spec"]}
        result_path = attempt.packaging / "smoke_report.json"
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 1
    args.timeout = int(ExecutionSpec.from_dict(meta["execution_spec"]).timeout_seconds)
    required = [task / "instruction.md", task / "task.toml", task / "tests/test.sh",
                task / "tests/test.patch", task / "tests/grader.py", task / "environment/Dockerfile"]
    errors = [f"missing:{path.relative_to(attempt.root)}" for path in required if not path.is_file()]
    result_path = attempt.packaging / "smoke_report.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    if errors:
        result = {"status": "FAIL", "failure_domain": "package", "errors": errors}
        result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 1

    log_dir = attempt.packaging / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "artifacts").mkdir(exist_ok=True)
    # The smoke test evaluates the published test patch against the known-good
    # implementation, so it checks package wiring independently of the build
    # workspace used by construction replay.  In particular, start from a
    # clean Base checkout: ``before_repo_set_cmd`` restores the historical
    # post-PR test files for replay, while ``tests/test.patch`` is precisely
    # the patch that must install those files in a packaged task.  Reusing the
    # replay command here would apply the same test change twice.
    (log_dir / "artifacts/model.patch").write_text(
        (root / "sealed/gold.patch").read_text(encoding="utf-8"), encoding="utf-8"
    )
    script = """
set +e
cd /app
eval "$BASE_STATE_CMD"
setup_rc=$?
if [ "$setup_rc" -eq 0 ]; then bash /tests/test.sh; test_rc=$?; else test_rc=125; fi
echo "__SMOKE_SETUP_RC=$setup_rc"
echo "__SMOKE_TEST_RC=$test_rc"
exit 0
"""
    command = [
        "docker", "run", "--rm", "--network", "none", "--entrypoint", "/bin/bash",
        "-v", f"{(task / 'tests').resolve()}:/tests:ro",
        "-v", f"{log_dir.resolve()}:/logs",
        "-e", f"BASE_STATE_CMD={build_base_state_script(meta['base_commit'], '')}",
        meta["docker_image"], "-c", script,
    ]
    try:
        proc = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              timeout=args.timeout, check=False)
        output, timed_out = proc.stdout, False
    except subprocess.TimeoutExpired as exc:
        raw = exc.stdout or ""
        output = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
        output += "\nTIMEOUT\n"
        timed_out = True
    (log_dir / "smoke.log").write_text(output, encoding="utf-8")
    setup = re.search(r"^__SMOKE_SETUP_RC=(\d+)$", output, re.MULTILINE)
    test = re.search(r"^__SMOKE_TEST_RC=(\d+)$", output, re.MULTILINE)
    setup_rc, test_rc = (int(setup.group(1)) if setup else None), (int(test.group(1)) if test else None)
    status = "PASS" if not timed_out and setup_rc == 0 and test_rc == 0 else "FAIL"
    result = {
        "status": status, "setup_rc": setup_rc, "test_rc": test_rc, "timed_out": timed_out,
        "failure_domain": None if status == "PASS" else "package",
        "log": str((log_dir / "smoke.log").resolve()),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
