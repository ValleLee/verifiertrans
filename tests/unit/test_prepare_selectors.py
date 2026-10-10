from pathlib import Path

from src.verifier_trans.deterministic.preparation.prepare_instance import _preflight_test_files


def test_go_bare_selectors_use_test_patch_files(tmp_path: Path):
    workspace = tmp_path / "workspace"
    repo = workspace / "public" / "repo"
    target = repo / "core" / "agents" / "lastfm" / "agent_test.go"
    target.parent.mkdir(parents=True)
    target.write_text("package lastfm\n", encoding="utf-8")
    restricted = workspace / "restricted"
    restricted.mkdir(parents=True)
    (restricted / "original_test.patch").write_text(
        "diff --git a/core/agents/lastfm/agent_test.go b/core/agents/lastfm/agent_test.go\n"
        "--- a/core/agents/lastfm/agent_test.go\n"
        "+++ b/core/agents/lastfm/agent_test.go\n",
        encoding="utf-8",
    )

    files = _preflight_test_files(
        workspace, repo,
        {"selected_test_files_to_run": ["TestLastFM"], "fail_to_pass": ["TestLastFM"], "pass_to_pass": []},
        "go",
    )

    assert files == {"core/agents/lastfm/agent_test.go"}


def test_go_preflight_discovers_packages_without_compiling_base_f2p_tests():
    source = Path("src/verifier_trans/deterministic/preparation/prepare_instance.py").read_text(encoding="utf-8")
    assert "go list -buildvcs=false ./..." in source
    assert "go test ./... -run '^$'" not in source
