from pathlib import Path


def test_verifier_replay_delegates_runtime_to_execution_adapter() -> None:
    source = Path("src/verifier_trans/deterministic/replay/verifier.py").read_text(
        encoding="utf-8"
    )
    assert "execution_plan(workspace, meta, group)" in source
    assert "execution_command = plan.command" in source
    assert "for host_path, container_path in plan.mounts" in source


def test_candidate_replay_delegates_runtime_to_execution_adapter() -> None:
    source = Path("src/verifier_trans/deterministic/replay/candidate.py").read_text(
        encoding="utf-8"
    )
    assert "execution_plan(workspace, meta, execution_group)" in source
    assert "execution_command = plan.command" in source


def test_replay_bootstraps_optional_local_redis_service() -> None:
    verifier = Path("src/verifier_trans/deterministic/replay/verifier.py").read_text(
        encoding="utf-8"
    )
    candidate = Path("src/verifier_trans/deterministic/replay/candidate.py").read_text(
        encoding="utf-8"
    )
    services = Path("src/verifier_trans/deterministic/execution/services.py").read_text(
        encoding="utf-8"
    )
    for source in (verifier, candidate):
        assert "redis_bootstrap_script" in source
    assert "command -v redis-cli" in services
    assert "redis-server --daemonize yes" in services
    assert "for _ in $(seq 1 30)" in services
