from pathlib import Path


def test_candidate_replay_does_not_materialize_model_runtime() -> None:
    source = Path("src/verifier_trans/deterministic/replay/candidate.py").read_text(
        encoding="utf-8"
    )
    assert "execution_plan" in source
    assert "cp -f /workspace/framework/p2p_runner.py" not in source
    assert "mkdir -p /app/framework" not in source
    assert '"INFRASTRUCTURE"' in source
    assert "--no-preserve=all" in source
    assert '"uv_os_get_passwd"' in source
    assert source.index("for host_path, container_path in plan.mounts") < source.index(
        'command.extend([meta["docker_image"], "-c", script])'
    )
