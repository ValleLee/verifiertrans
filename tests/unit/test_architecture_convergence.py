import json
from pathlib import Path

import pytest

from verifier_trans.deterministic.execution import contract_environment_args, execution_plan, execution_spec_hash, parse_result_marker
from verifier_trans.deterministic.execution.services import service_bootstrap_script
from verifier_trans.deterministic.execution.discovery import ExecutionSpec
from verifier_trans.pipeline.qa import negative_execution_contract
from verifier_trans.pipeline import orchestrator
from verifier_trans.deterministic.packaging.package_task import verifier_files


def _spec(**overrides):
    value = ExecutionSpec(
        "node", "jest", "npm", "packages/app", "packages/app",
        "file-and-test-name", (), None, True, "frozen",
    ).as_dict()
    value.update(overrides)
    return value


def test_replay_consumes_frozen_execution_spec_instead_of_rediscovering(tmp_path: Path):
    repo = tmp_path / "public" / "repo"
    repo.mkdir(parents=True)
    (repo / "package.json").write_text('{"scripts":{"test":"mocha"}}', encoding="utf-8")
    verifier = tmp_path / "verifier"
    verifier.mkdir()
    (verifier / "functional_impl.js").write_text("", encoding="utf-8")
    (verifier / "manifest.json").write_text(
        json.dumps({"functional_artifact": "functional_impl.js"}), encoding="utf-8"
    )
    plan = execution_plan(tmp_path, {"repo_language": "javascript", "execution_spec": _spec()}, "f2p")
    assert plan.spec.runner_family == "jest"
    assert "/app/packages/app" in plan.command


def test_manifest_is_authoritative_and_filename_scan_is_not_used(tmp_path: Path):
    verifier = tmp_path / "verifier"
    verifier.mkdir()
    (verifier / "functional_f2p.js").write_text("", encoding="utf-8")
    (verifier / "manifest.json").write_text(json.dumps({"f2p_command": "legacy"}), encoding="utf-8")
    with pytest.raises(ValueError, match="functional_artifact"):
        execution_plan(tmp_path, {"repo_language": "javascript", "execution_spec": _spec()}, "f2p")


def test_package_manifest_cannot_fallback_to_directory_scan(tmp_path: Path):
    verifier = tmp_path / "verifier"
    verifier.mkdir()
    (verifier / "functional_impl.py").write_text("", encoding="utf-8")
    (verifier / "manifest.json").write_text(
        json.dumps({"functional_artifact": "functional_impl.py", "f2p_command": "legacy", "p2p_command": "legacy"}), encoding="utf-8"
    )
    with pytest.raises(SystemExit, match="test_files"):
        verifier_files(tmp_path)


def test_python_selector_uses_frozen_cwd(tmp_path: Path):
    verifier = tmp_path / "verifier"
    verifier.mkdir()
    (verifier / "functional.py").write_text("", encoding="utf-8")
    (verifier / "manifest.json").write_text(json.dumps({"functional_artifact": "functional.py"}), encoding="utf-8")
    spec = _spec(language="python", runner_family="pytest", selector_style="file-and-node", cwd="src")
    plan = execution_plan(tmp_path, {"repo_language": "python", "execution_spec": spec}, "p2p")
    assert plan.command.startswith("cd /app/src &&")


def test_service_bootstrap_is_contract_gated():
    assert service_bootstrap_script(ExecutionSpec("python", "pytest", "pip", ".", ".", "x", (), None, True, "x")) == ":"
    with pytest.raises(ValueError, match="unsupported execution services"):
        service_bootstrap_script(ExecutionSpec("python", "pytest", "pip", ".", ".", "x", ("mysql",), None, True, "x"))


def test_execution_contract_has_stable_hash_and_shared_marker_parser():
    spec = ExecutionSpec("python", "pytest", "pip", ".", ".", "x", (), None, True, "x")
    assert execution_spec_hash(spec) == execution_spec_hash(ExecutionSpec.from_dict(spec.as_dict()))
    assert parse_result_marker("__SOL_VERIFIER_RC=0\n", "__SOL", "VERIFIER_RC") == 0
    env_spec = ExecutionSpec("python", "pytest", "pip", ".", ".", "x", (), None, True, "x", (("APP_MODE", "test"),))
    assert contract_environment_args(env_spec) == ("-e", "APP_MODE=test")


def test_negative_contract_distinguishes_rejection_false_positive_and_infrastructure():
    good = {"accepted": True}
    rejected = negative_execution_contract(True, good, {"accepted": False})
    assert rejected["accepted"] is True and rejected["failure_class"] == "NONE"
    false_positive = negative_execution_contract(True, good, good)
    assert false_positive["false_positive"] is True and false_positive["repair_required"] is True
    infra = negative_execution_contract(True, good, {"accepted": False, "failure_cause": "timeout"})
    assert infra["accepted"] is False and infra["failure_class"] == "INFRASTRUCTURE"
    semantic = negative_execution_contract(True, good, {"accepted": False, "failure_cause": "verifier"})
    assert semantic["accepted"] is True and semantic["failure_class"] == "NONE"


def test_accumulated_evidence_replay_routes_semantic_and_infra_separately(monkeypatch, tmp_path: Path):
    calls = []

    def fake_run_candidate(_workspace, name, _config, group, parent=None, revision=0):
        calls.append((name, group, parent, revision))
        if name == "positive":
            return {"accepted": group != "legacy_f2p", "runnable": True}
        if group == "p2p":
            return {"accepted": True, "runnable": True}
        return {"accepted": False, "runnable": True, "failure_cause": "timeout" if name == "infra" else "verifier"}

    monkeypatch.setattr(orchestrator, "run_candidate", fake_run_candidate)
    evidence = {
        "positives": [{"name": "positive"}],
        "mutants": [{"name": "semantic", "parent": "positive", "judge": {"verdict": "RELEVANT_NON_EQUIVALENT"}},
                    {"name": "infra", "parent": "positive", "judge": {"verdict": "RELEVANT_NON_EQUIVALENT"}}],
    }
    result = orchestrator.replay_evidence(tmp_path, {}, evidence, revision=4)
    assert result["accepted"] is False
    assert result["failure_class"] == "INFRASTRUCTURE"
    semantic_row = next(row for row in result["mutants"] if row["name"] == "semantic")
    infra_row = next(row for row in result["mutants"] if row["name"] == "infra")
    assert semantic_row["accepted"] is True and semantic_row["failure_class"] == "NONE"
    assert infra_row["accepted"] is False and infra_row["failure_class"] == "INFRASTRUCTURE"
    assert {group for _, group, _, _ in calls} == {"p2p", "f2p", "legacy_f2p"}
