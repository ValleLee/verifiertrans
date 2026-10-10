from pathlib import Path

from verifier_trans.deterministic.validation.instruction_policy import audit_instruction_scope


def test_instruction_policy_allows_observable_contract(tmp_path: Path):
    path = tmp_path / "instruction_scope.md"
    path.write_text("Expose a public API and preserve the returned value.\nINSTRUCTION_SCOPE: PASS\n", encoding="utf-8")
    result = audit_instruction_scope(path)
    assert result["status"] == "PASS"
    assert result["hard_errors"] == []


def test_instruction_policy_marks_visibility_as_advisory(tmp_path: Path):
    path = tmp_path / "instruction_scope.md"
    path.write_text("External callers cannot construct the package-private transport client.\n", encoding="utf-8")
    result = audit_instruction_scope(path)
    assert result["status"] == "PASS"
    assert result["advisories"] == ["visibility_binding"]


def test_instruction_policy_rejects_test_and_layout_leakage(tmp_path: Path):
    path = tmp_path / "instruction_scope.md"
    path.write_text("Use tests/foo.py::test_bar and the exact file layout.\n", encoding="utf-8")
    result = audit_instruction_scope(path)
    assert result["status"] == "FAIL"
    assert "historical_selector" in result["hard_errors"]
    assert "gold_or_layout" in result["hard_errors"]
