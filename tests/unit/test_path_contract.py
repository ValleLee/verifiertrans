from pathlib import Path

from verifier_trans.deterministic.validation.path_contract import validate_artifact_paths


def make_workspace(tmp_path: Path, source: str) -> Path:
    (tmp_path / "public" / "repo" / "src").mkdir(parents=True)
    (tmp_path / "public" / "repo" / "src" / "feature.ts").write_text(
        "export const value = 1\n", encoding="utf-8"
    )
    (tmp_path / "verifier").mkdir()
    (tmp_path / "verifier" / "functional_tests.mjs").write_text(source, encoding="utf-8")
    return tmp_path


def test_relative_import_uses_app_repository_root(tmp_path: Path) -> None:
    result = validate_artifact_paths(make_workspace(tmp_path, 'import "../src/feature.ts"\n'))
    assert result["status"] == "PASS"


def test_relative_import_cannot_escape_app_root(tmp_path: Path) -> None:
    result = validate_artifact_paths(make_workspace(tmp_path, 'import "../../src/feature.ts"\n'))
    assert result["status"] == "FAIL"
    assert result["issues"][0]["reason"].startswith("outside_execution_root:")


def test_missing_local_artifact_module_is_rejected(tmp_path: Path) -> None:
    result = validate_artifact_paths(make_workspace(tmp_path, 'import "./missing.mjs"\n'))
    assert result["status"] == "FAIL"
    assert result["issues"][0]["reason"].startswith("missing_target:")
