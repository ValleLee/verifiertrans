from verifier_trans.deterministic.packaging.package_task import make_test_sh


def test_package_test_script_grades_only_current_f2p_and_retained_p2p() -> None:
    script = make_test_sh("python3 /app/verifier/functional_f2p.py", "python3 /tests/p2p_runner.py selectors")
    assert "legacy_f2p" not in script
    assert "functional_f2p.py" in script
    assert "p2p_runner.py" in script
