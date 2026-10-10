from pathlib import Path

from verifier_trans.agents.miniswe_session import (
    _copy_tree,
    _has_initial_verifier_artifact,
    _iter_converter_files,
)
from verifier_trans.pipeline.orchestrator import recover_partial_converter_artifact, reset_output


def test_converter_prompt_forbids_dependency_fetches() -> None:
    prompt = Path(__file__).parents[2].joinpath("prompts", "converter.md").read_text(encoding="utf-8")
    assert "npm pack" in prompt
    assert "pip install" in prompt
    assert "go get" in prompt
    assert "cargo fetch" in prompt


def test_converter_workspace_separates_scratch_and_formal_output() -> None:
    source = Path(__file__).parents[1].joinpath(
        "..", "src", "verifier_trans", "agents", "miniswe_session.py"
    ).resolve().read_text(encoding="utf-8")
    assert 'sandbox / "scratch"' in source
    assert 'sandbox / "output"' in source
    assert "compatibility alias" in source


def test_converter_prompt_audits_indirect_harness_coupling() -> None:
    prompt = Path(__file__).parents[2].joinpath("prompts", "converter.md").read_text(
        encoding="utf-8"
    )
    assert "Harness anti-coupling contract" in prompt
    assert "mock, fake object, fixture, monkeypatch, stub" in prompt
    assert "plausible alternative" in prompt
    assert "implementations" in prompt
    assert "missing mock property/method" in prompt
    assert "Harness contract" in prompt


def test_semantic_judge_prompt_audits_mock_fixture_coupling() -> None:
    prompt = Path(__file__).parents[2].joinpath(
        "prompts", "judges", "semantic.md"
    ).read_text(encoding="utf-8")
    assert "Mock/Fixture-Induced Implementation Coupling" in prompt
    assert "synthetic runtime object" in prompt
    assert "equivalent standard properties/methods" in prompt


def test_agent_shell_wraps_docker_commands_with_in_container_timeout() -> None:
    source = Path(__file__).parents[1].joinpath(
        "..", "src", "verifier_trans", "agents", "miniswe_session.py"
    ).resolve().read_text(encoding="utf-8")
    assert "timeout --signal=TERM --kill-after=5s" in source


def test_positive_prompt_forbids_dependency_fetches() -> None:
    prompt = Path(__file__).parents[2].joinpath(
        "prompts", "qa", "positive_generator.md"
    ).read_text(encoding="utf-8")
    assert "npm install" in prompt
    assert "cargo fetch" in prompt


def test_converter_snapshot_skips_scratch_dependency_trees(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "tmp_mithril" / "package").mkdir(parents=True)
    (source / "tmp_mithril" / "package" / "domMock.js").write_text("scratch", encoding="utf-8")
    (source / "functional_verifier.mjs").write_text("verifier", encoding="utf-8")

    assert [path.name for path in _iter_converter_files(source)] == ["functional_verifier.mjs"]

    target = tmp_path / "target"
    _copy_tree(source, target, ignore_converter_scratch=True)
    assert (target / "functional_verifier.mjs").read_text(encoding="utf-8") == "verifier"
    assert not (target / "tmp_mithril").exists()


def test_failed_converter_staging_becomes_repair_context(tmp_path: Path) -> None:
    staging = tmp_path / "artifacts" / "staging" / "converter_rev_001_session"
    staging.mkdir(parents=True)
    (staging / "functional_tests.ts").write_text("partial", encoding="utf-8")

    packet = recover_partial_converter_artifact(tmp_path, RuntimeError("step limit"))

    assert packet is not None
    assert (tmp_path / "verifier" / "functional_tests.ts").read_text(encoding="utf-8") == "partial"
    assert packet["core_gate"]["partial_files"] == ["functional_tests.ts"]


def test_initial_verifier_detection_is_language_neutral(tmp_path: Path) -> None:
    verifier = tmp_path / "verifier"
    verifier.mkdir()
    (verifier / "functional_tests.ts").write_text("", encoding="utf-8")
    assert _has_initial_verifier_artifact(verifier)


def test_reset_output_preserves_compatibility_symlink(tmp_path: Path) -> None:
    target = tmp_path / "current"
    target.mkdir()
    (target / "old.txt").write_text("old", encoding="utf-8")
    compat = tmp_path / "verifier"
    compat.symlink_to(target, target_is_directory=True)

    reset_output(compat)

    assert compat.is_symlink()
    assert target.is_dir()
    assert not (target / "old.txt").exists()
