from pathlib import Path


def test_candidate_replay_mounts_adapter_paths() -> None:
    source = Path("src/verifier_trans/deterministic/replay/candidate.py").read_text()
    assert "for host_path, container_path in plan.mounts" in source
    assert ":/restricted/resolved_test_selectors.json:ro" in source
