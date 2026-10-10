#!/usr/bin/env python3
"""Apply one validator solution to a clean baseline and run the converted verifier.

Used by the Solution Diversity measurement.  The result is a *metric*, not a
gate: a rejection may mean the verifier is over-fitted to the reference
implementation, or that the solution is simply wrong, and only adjudication can
tell those apart.  Nothing here modifies the verifier.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from ..execution import contract_environment_args, execution_plan, execution_spec_hash, parse_result_marker, standard_role_mounts
from ..execution.services import redis_bootstrap_script, service_bootstrap_script
from ..preparation.common import build_base_state_script
from ..validation.artifact_contract import add_contract

_SETUP_FAILED = 125


def solution_files(solution_dir: Path) -> list[Path]:
    return [
        path for path in sorted(solution_dir.rglob("*"))
        if path.is_file() and path.name != "NOTES.md"
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--solution", required=True)
    parser.add_argument("--group", choices=("all", "f2p", "p2p", "legacy_f2p"), default="all")
    parser.add_argument("--parent-solution", help="merge this known-valid payload before the candidate")
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--revision", type=int, default=0)
    args = parser.parse_args()

    workspace = args.workspace.resolve()
    solution_dir = workspace / "run" / "validator" / args.solution
    if not solution_dir.is_dir():
        raise SystemExit(f"no such solution directory: {solution_dir}")
    meta = json.loads((workspace / "run" / "metadata.json").read_text(encoding="utf-8"))
    if not isinstance(meta.get("execution_spec"), dict):
        raise ValueError("missing frozen execution_spec; candidate replay cannot rediscover runner metadata")
    plan = execution_plan(workspace, meta, args.group if args.group != "all" else "f2p")
    if plan.spec is not None:
        args.timeout = int(plan.spec.timeout_seconds)
    log_dir = workspace / "run" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"validator_{args.solution.replace('/', '_')}_{args.group}.log"
    # Solution names may be nested (the negative probe uses
    # ``negative/partial``).  Keep the evidence layout namespaced without
    # assuming the log filename's parent is already present.
    log_path.parent.mkdir(parents=True, exist_ok=True)

    files = solution_files(solution_dir)
    # A solution that ships nothing cannot be evaluated; record it as such
    # rather than counting a vacuous pass.
    if not files:
        payload = {
            "solution": args.solution, "accepted": None, "failure_cause": "empty_solution",
            "files": 0, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        result = add_contract(workspace, args.revision, payload,
                              status="FAIL", failure_class="VERIFIER_SEMANTIC")
        result_name = f"{args.solution}.{args.group}.json" if args.group != "all" else f"{args.solution}.json"
        (workspace / "run" / "validator" / result_name).write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(result, indent=2))
        return 1

    parent_dir = Path(args.parent_solution).resolve() if args.parent_solution else None
    if parent_dir is not None and not parent_dir.is_dir():
        raise SystemExit(f"parent solution directory does not exist: {parent_dir}")
    # Do not preserve the solver container's uid/gid when materializing a
    # candidate.  Solver payloads are commonly written by an unprivileged
    # user; preserving that ownership can make the repository's native Node
    # runner resolve a uid absent from /etc/passwd (uv_os_get_passwd ENOENT).
    copy_flags = "cp -r --no-preserve=all"
    parent_step = f"{copy_flags} /parent/. /app/\nparent_rc=$?" if parent_dir else "parent_rc=0"
    execution_group = args.group if args.group != "all" else "f2p"
    plan = execution_plan(workspace, meta, execution_group)
    execution_command = plan.command
    service_bootstrap = service_bootstrap_script(plan.spec)
    script = f'''
set +e
cd /app
eval "$BASE_STATE_CMD"
setup_rc=$?
if [ "$setup_rc" -ne 0 ]; then
  echo "__SOL_SETUP_RC=$setup_rc"; echo "__SOL_APPLY_RC=125"; echo "__SOL_VERIFIER_RC=125"; exit 0
fi
echo "__SOL_SETUP_RC=0"
# Apply the solution onto the baseline working tree, then run the verifier.
{parent_step}
{copy_flags} /solution/. /app/
candidate_rc=$?
apply_rc=$((parent_rc || candidate_rc))
echo "__SOL_APPLY_RC=$apply_rc"
if [ "$apply_rc" -eq 0 ]; then
  {service_bootstrap}
  {execution_command}
  verifier_rc=$?
else
  verifier_rc=125
fi
echo "__SOL_VERIFIER_RC=$verifier_rc"
'''
    command = [
        "docker", "run", "--rm", "--network", "none", "--entrypoint", "/bin/bash",
        "-v", f"{solution_dir.resolve()}:/solution:ro",
        *(["-v", f"{parent_dir}:/parent:ro"] if parent_dir else []),
        "-e", f"BASE_STATE_CMD={build_base_state_script(meta['base_commit'], meta['before_repo_set_cmd'])}",
    ]
    for host_path, container_path in standard_role_mounts(workspace, log_dir):
        # Canonical selector mount is rendered as :/restricted/resolved_test_selectors.json:ro
        suffix = ":ro" if container_path != "/logs" else ""
        command.extend(["-v", f"{host_path.resolve()}:{container_path}{suffix}"])
    command.extend(contract_environment_args(plan.spec))
    for host_path, container_path in plan.mounts:
        command.extend(["-v", f"{host_path.resolve()}:{container_path}:ro"])
    command.extend([meta["docker_image"], "-c", script])
    try:
        proc = subprocess.run(
            command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=args.timeout, check=False,
        )
        output, timed_out = proc.stdout, False
    except subprocess.TimeoutExpired as exc:
        raw = exc.stdout or ""
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        output, timed_out = raw + "\nTIMEOUT\n", True
    log_path.write_text(output, encoding="utf-8")

    def marker(name: str) -> int | None:
        return parse_result_marker(output, "__SOL", name)

    setup_rc, apply_rc, verifier_rc = marker("SETUP_RC"), marker("APPLY_RC"), marker("VERIFIER_RC")
    runnable = not timed_out and setup_rc == 0 and apply_rc == 0 and verifier_rc not in (None, _SETUP_FAILED)
    toolchain_missing = (
        "mocha binary not found" in output.lower()
        or "no module named pytest" in output.lower()
    )
    environment_missing = "uv_os_get_passwd" in output.lower()
    docker_unavailable = any(
        phrase in output.lower()
        for phrase in (
            "permission denied while trying to connect to the docker daemon",
            "cannot connect to the docker daemon",
            "is the docker daemon running",
        )
    )
    payload = {
        "solution": args.solution,
        "group": args.group,
        "files": len(files),
        "timed_out": timed_out,
        "setup_rc": setup_rc,
        "apply_rc": apply_rc,
        "verifier_rc": verifier_rc,
        "runnable": runnable,
        "accepted": (verifier_rc == 0) if runnable else None,
        "failure_cause": (
            "timeout" if timed_out
            else "setup_failed" if setup_rc not in (0, None)
            else "apply_failed" if apply_rc not in (0, None)
            else "docker_unavailable" if docker_unavailable
            else "environment_missing" if environment_missing
            else "toolchain_missing" if toolchain_missing
            else "verifier" if verifier_rc is not None
            else "no_marker"
        ),
        "failure_excerpt": output[-4000:] if verifier_rc not in (0, None) else "",
        "log": str(log_path.resolve()),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "execution_spec_hash": execution_spec_hash(plan.spec) if plan.spec is not None else None,
    }
    result_accepted = payload["accepted"] is True
    framework_runner_missing = (
        "p2p_runner.py" in output and
        ("No such file or directory" in output or "can't open file" in output)
    )
    failure_class = "NONE" if result_accepted else (
        "INFRASTRUCTURE" if payload["failure_cause"] in
        {"timeout", "setup_failed", "apply_failed", "no_marker", "toolchain_missing",
         "docker_unavailable", "environment_missing"}
        or framework_runner_missing
        else "VERIFIER_SEMANTIC"
    )
    result = add_contract(workspace, args.revision, payload,
                          status="PASS" if result_accepted else "FAIL",
                          failure_class=failure_class)
    result_name = f"{args.solution}.{args.group}.json" if args.group != "all" else f"{args.solution}.json"
    (workspace / "run" / "validator" / result_name).write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in result.items() if k != "failure_excerpt"}, indent=2))
    return 0 if result["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
