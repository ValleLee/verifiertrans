#!/usr/bin/env python3
"""Run converted F2P and retained P2P groups on clean Base/Gold states."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from ..execution import contract_environment_args, execution_plan, execution_spec_hash, parse_result_marker, standard_role_mounts
from ..execution.services import redis_bootstrap_script, service_bootstrap_script
from ..preparation.common import build_base_state_script, classify_results, normalize_node_id
from ..validation.artifact_contract import add_contract

SETUP_FAILED = 125
GROUPS = ("f2p", "p2p", "legacy_f2p")


def execution_failure(output: str, verifier_rc: int | None) -> str | None:
    text = str(output or "")
    lowered = text.lower()
    if "permission denied while trying to connect to the docker daemon" in lowered:
        return "docker_unavailable"
    if "cannot connect to the docker daemon" in lowered or "is the docker daemon running" in lowered:
        return "docker_unavailable"
    if verifier_rc == 127 and "command not found" in lowered:
        return "toolchain_missing"
    if "mocha binary not found" in lowered or "no module named pytest" in lowered:
        return "toolchain_missing"
    if "no usable python 3 interpreter with pytest" in lowered:
        return "toolchain_missing"
    return None


def infra_failure(check: dict) -> bool:
    """Return whether a replay result is an execution/infrastructure failure.

    Keep this classification local to the deterministic replay script so its
    final artifact can be classified without importing the orchestrator.
    Verifier assertion failures are deliberately excluded.
    """
    if check.get("failure_cause") in {
        "docker_unavailable", "toolchain_missing", "timeout",
        "setup_failed", "patch_failed", "no_marker",
    }:
        return True
    return False


def build_replay_command(
    workspace: Path, meta: dict, plan, script: str, log_dir: Path,
) -> list[str]:
    """Build the Docker replay command with all mounts before the image.

    Docker parses options only before the image reference.  Keeping this
    assembly in one helper prevents execution-adapter mounts (for example the
    framework-owned P2P runner) from being silently treated as container
    arguments.
    """
    command = ["docker", "run", "--rm", "--network", "none", "--entrypoint", "/bin/bash"]
    for host_path, container_path in standard_role_mounts(workspace, log_dir):
        suffix = ":ro" if container_path != "/logs" else ""
        command.extend(["-v", f"{host_path.resolve()}:{container_path}{suffix}"])
    command.extend(["-e", f"BASE_STATE_CMD={build_base_state_script(meta['base_commit'], meta['before_repo_set_cmd'])}"])
    plan_spec = getattr(plan, "spec", None)
    if plan_spec is not None:
        command.extend(contract_environment_args(plan_spec))
    for host_path, container_path in plan.mounts:
        command.extend(["-v", f"{host_path.resolve()}:{container_path}:ro"])
    command.extend([meta["docker_image"], "-c", script])
    return command


def run_state(workspace: Path, state: str, group: str, timeout: int, label: str) -> dict:
    if group not in GROUPS:
        raise ValueError(f"unsupported verifier group: {group}")
    meta = json.loads((workspace / "run" / "metadata.json").read_text(encoding="utf-8"))
    if not isinstance(meta.get("execution_spec"), dict):
        raise ValueError("missing frozen execution_spec; replay cannot rediscover runner metadata")
    plan = execution_plan(workspace, meta, group)
    # The frozen contract, not each caller's CLI default, owns execution time.
    if plan.spec is not None:
        timeout = int(plan.spec.timeout_seconds)
    log_dir = workspace / "run" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{label}_{state.lower()}_{group}.log"
    patch_step = (
        "git apply --check /sealed/gold.patch\n"
        "patch_check_rc=$?\n"
        'if [ "$patch_check_rc" -eq 0 ]; then git apply /sealed/gold.patch; patch_rc=$?; '
        'else patch_rc=$patch_check_rc; fi\n'
        if state == "Gold"
        else "patch_check_rc=0\npatch_rc=0\n"
    )
    # The Converter declares the functional artifact; the deterministic
    # execution adapter supplies the language-native command and selector
    # runner.  This keeps Docker cwd/mount/service details out of the model
    # generated verifier.
    execution_command = plan.command
    service_bootstrap = service_bootstrap_script(plan.spec)
    script = f'''
set +e
cd /app
eval "$BASE_STATE_CMD"
setup_rc=$?
{patch_step}
if [ "$setup_rc" -eq 0 ] && [ "$patch_rc" -eq 0 ]; then
  {service_bootstrap}
  {execution_command}
  verifier_rc=$?
else
  verifier_rc={SETUP_FAILED}
fi
echo "__CONV_SETUP_RC=$setup_rc"
echo "__CONV_PATCH_CHECK_RC=$patch_check_rc"
echo "__CONV_PATCH_RC=$patch_rc"
echo "__CONV_VERIFIER_RC=$verifier_rc"
'''
    command = build_replay_command(workspace, meta, plan, script, log_dir)
    try:
        result = subprocess.run(
            command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=timeout, check=False,
        )
        output, timed_out, container_rc = result.stdout, False, result.returncode
    except subprocess.TimeoutExpired as exc:
        raw = exc.stdout or ""
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        output, timed_out, container_rc = raw + "\nTIMEOUT\n", True, None
    log_path.write_text(output, encoding="utf-8")

    def marker(name: str) -> int | None:
        return parse_result_marker(output, "__CONV", name)

    setup_rc = marker("SETUP_RC")
    patch_check_rc = marker("PATCH_CHECK_RC")
    patch_rc = marker("PATCH_RC")
    verifier_rc = marker("VERIFIER_RC")
    cause = execution_failure(output, verifier_rc)
    runnable = (
        not timed_out
        and setup_rc == 0
        and patch_rc == 0
        and verifier_rc is not None
        and verifier_rc != SETUP_FAILED
        and cause is None
    )
    return {
        "state": state,
        "group": group,
        "label": label,
        "container_exit_code": container_rc,
        "timed_out": timed_out,
        "setup_rc": setup_rc,
        "patch_check_rc": patch_check_rc,
        "patch_rc": patch_rc,
        "verifier_rc": verifier_rc,
        "runnable": runnable,
        "passed": verifier_rc == 0 if runnable else None,
        "failure_cause": (
            "timeout" if timed_out
            else "setup_failed" if setup_rc not in (0, None)
            else "patch_failed" if patch_rc not in (0, None)
            else cause if cause is not None
            else "verifier" if verifier_rc is not None
            else "no_marker"
        ),
        "log": str(log_path.resolve()),
        "execution_spec_hash": execution_spec_hash(plan.spec) if plan.spec is not None else None,
    }


def parse_node_results(log_text: str, language: str) -> dict[str, bool]:
    results: dict[str, bool] = {}
    patterns = (
        re.compile(r"^(?P<node>\S+::\S+)\s+(?P<outcome>PASSED|FAILED|ERROR|SKIPPED)\b"),
        re.compile(r"(?P<outcome>ok|not ok)\s+\d+\s+(?P<node>.+?)$"),
    )
    for raw in log_text.splitlines():
        line = raw.strip()
        for pattern in patterns:
            match = pattern.match(line)
            if not match:
                continue
            node = normalize_node_id(match.group("node"), language)
            outcome = match.group("outcome")
            results[node] = outcome in ("PASSED", "ok")
            break
    return results


def one_replay(workspace: Path, timeout: int, label: str) -> dict:
    base_f2p = run_state(workspace, "Base", "f2p", timeout, label)
    gold_f2p = run_state(workspace, "Gold", "f2p", timeout, label)
    base_p2p = run_state(workspace, "Base", "p2p", timeout, label)
    gold_p2p = run_state(workspace, "Gold", "p2p", timeout, label)
    return {
        "base_f2p": base_f2p,
        "gold_f2p": gold_f2p,
        "base_p2p": base_p2p,
        "gold_p2p": gold_p2p,
    }


def accepted(replay: dict) -> bool:
    return bool(
        replay["base_f2p"]["runnable"]
        and replay["gold_f2p"]["runnable"]
        and replay["base_p2p"]["runnable"]
        and replay["gold_p2p"]["runnable"]
        and replay["base_f2p"]["passed"] is False
        and replay["gold_f2p"]["passed"] is True
        and replay["base_p2p"]["passed"] is True
        and replay["gold_p2p"]["passed"] is True
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--round", type=int, default=1)
    parser.add_argument("--repeat", type=int, default=2)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    run_sh = workspace / "verifier" / "run.sh"
    metadata_path = workspace / "run" / "metadata.json"
    if not run_sh.is_file():
        raise SystemExit(f"missing verifier entrypoint: {run_sh}")
    if not metadata_path.is_file():
        raise SystemExit(f"missing metadata: {metadata_path}")

    repeats = max(1, args.repeat)
    replays = [one_replay(workspace, args.timeout, f"round_{args.round}_repeat_{i + 1}") for i in range(repeats)]
    first = replays[0]
    signatures = [
        (
            replay["base_f2p"]["runnable"], replay["base_f2p"]["passed"],
            replay["gold_f2p"]["runnable"], replay["gold_f2p"]["passed"],
            replay["base_p2p"]["runnable"], replay["base_p2p"]["passed"],
            replay["gold_p2p"]["runnable"], replay["gold_p2p"]["passed"],
        )
        for replay in replays
    ]
    stable = len(set(signatures)) == 1
    meta = json.loads(metadata_path.read_text(encoding="utf-8"))
    resolved_path = workspace / "restricted" / "resolved_test_selectors.json"
    seeds_path = workspace / "restricted" / "test_seeds.json"
    resolved = json.loads(resolved_path.read_text(encoding="utf-8")) if resolved_path.is_file() else {}
    seeds = json.loads(seeds_path.read_text(encoding="utf-8")) if seeds_path.is_file() else {}
    language = str(meta.get("repo_language") or "")
    base_nodes = parse_node_results(Path(first["base_f2p"]["log"]).read_text(encoding="utf-8", errors="replace"), language)
    gold_nodes = parse_node_results(Path(first["gold_f2p"]["log"]).read_text(encoding="utf-8", errors="replace"), language)
    inherited_p2p = list(
        ((resolved.get("pass_to_pass") or {}).get("resolved"))
        or [normalize_node_id(node, language) for node in seeds.get("pass_to_pass_source", [])]
    )
    observed_nodes = sorted(set(base_nodes) | set(gold_nodes))
    node_diff = (
        classify_results(
            {node: base_nodes.get(node, False) for node in observed_nodes},
            {node: gold_nodes.get(node, False) for node in observed_nodes},
            inherited_p2p,
        )
        if observed_nodes else None
    )
    payload = {
        "round": args.round,
        "repeat": repeats,
        "execution_spec_hash": first["base_f2p"].get("execution_spec_hash"),
        "accepted": accepted(first) and stable,
        "stable": stable,
        "verifier_runnable": all(
            replay[group]["runnable"]
            for replay in replays
            for group in ("base_f2p", "gold_f2p", "base_p2p", "gold_p2p")
        ),
        "base_pass": first["base_f2p"]["passed"],
        "gold_pass": first["gold_f2p"]["passed"],
        "p2p_pass": first["gold_p2p"]["passed"],
        "base_p2p_pass": first["base_p2p"]["passed"],
        "base_f2p": first["base_f2p"],
        "gold_f2p": first["gold_f2p"],
        "base_p2p": first["base_p2p"],
        "gold_p2p": first["gold_p2p"],
        "replays": replays,
        "node_diff": node_diff,
        "inherited_p2p_total": len(inherited_p2p),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    check = add_contract(
        workspace, args.round, payload,
        status="PASS" if payload["accepted"] else "FAIL",
        failure_class=("NONE" if payload["accepted"] else
                        "INFRASTRUCTURE" if any(infra_failure(payload[key]) for key in
                                                 ("base_f2p", "gold_f2p", "base_p2p", "gold_p2p"))
                        else "VERIFIER_SEMANTIC"),
    )
    (workspace / "run" / "check.json").write_text(
        json.dumps(check, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        key: check[key]
        for key in ("round", "repeat", "accepted", "stable", "verifier_runnable", "base_pass", "gold_pass", "base_p2p_pass", "p2p_pass")
    }, ensure_ascii=False, indent=2))
    return 0 if check["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
