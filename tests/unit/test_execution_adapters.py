import json
from pathlib import Path
from types import SimpleNamespace

from verifier_trans.deterministic.execution import execution_plan, discover_execution_spec, package_execution_plan
from verifier_trans.deterministic.replay.verifier import build_replay_command


def test_node_adapter_runs_functional_artifact_and_native_selector_runner(tmp_path: Path) -> None:
    (tmp_path / "verifier").mkdir()
    (tmp_path / "verifier" / "functional_f2p.js").write_text("", encoding="utf-8")
    metadata = {"repo_language": "javascript"}

    f2p = execution_plan(tmp_path, metadata, "f2p")
    p2p = execution_plan(tmp_path, metadata, "p2p")
    legacy = execution_plan(tmp_path, metadata, "legacy_f2p")

    assert "cd /app/." in f2p.command
    assert "VERIFIER_REPO_ROOT=/app" in f2p.command
    assert f2p.command.endswith("node /app/verifier/functional_f2p.js")
    assert "node /framework/node_p2p_runner.js" in p2p.command
    assert "pass_to_pass" in p2p.command
    assert "fail_to_pass" in legacy.command
    assert p2p.mounts and p2p.mounts[0][1] == "/framework/node_p2p_runner.js"


def test_functional_adapter_discovers_descriptive_multilanguage_artifact_name(tmp_path: Path) -> None:
    (tmp_path / "verifier").mkdir()
    (tmp_path / "verifier" / "functional_xss_verifier.cjs").write_text("", encoding="utf-8")
    plan = execution_plan(tmp_path, {"repo_language": "typescript"}, "f2p")
    assert plan.adapter == "node"
    assert "VERIFIER_REPO_ROOT=/app" in plan.command
    assert plan.command.endswith("node /app/verifier/functional_xss_verifier.cjs")


def test_python_adapter_uses_framework_replay_runner(tmp_path: Path) -> None:
    (tmp_path / "verifier").mkdir()
    (tmp_path / "verifier" / "functional_f2p.py").write_text("", encoding="utf-8")
    plan = execution_plan(tmp_path, {"repo_language": "python"}, "p2p")
    assert "python3 /framework/p2p_runner.py" in plan.command
    assert plan.mounts[0][0].name == "p2p_runner.py"


def test_replay_runner_mounts_are_before_docker_image(tmp_path: Path) -> None:
    plan = SimpleNamespace(mounts=((tmp_path / "runner.py", "/framework/p2p_runner.py"),))
    meta = {
        "docker_image": "example/repo:test",
        "base_commit": "base",
        "before_repo_set_cmd": "true",
    }
    command = build_replay_command(tmp_path, meta, plan, "true", tmp_path / "logs")
    image_index = command.index("example/repo:test")
    assert command[image_index - 1].endswith(":/framework/p2p_runner.py:ro")
    assert command[image_index + 1:image_index + 3] == ["-c", "true"]


def test_execution_spec_discovers_node_runner_and_typescript_loader(tmp_path: Path) -> None:
    repo = tmp_path / "public" / "repo"
    repo.mkdir(parents=True)
    (repo / "package.json").write_text(
        '{"scripts":{"test":"vitest run"},"devDependencies":{"vitest":"^1","tsx":"^4"}}',
        encoding="utf-8",
    )
    (repo / "tsconfig.json").write_text("{}", encoding="utf-8")
    spec = discover_execution_spec(repo, {"repo_language": "typescript"})
    assert spec.runner_family == "vitest"
    assert spec.typescript_loader == "tsx"
    assert spec.selector_style == "file-and-test-name"
    plan = execution_plan(tmp_path, {"repo_language": "typescript"}, "p2p")
    assert plan.spec == spec
    assert "--runner vitest" in plan.command
    assert "--loader none" in plan.command


def test_jest_functional_artifact_uses_native_runner(tmp_path: Path) -> None:
    repo = tmp_path / "public" / "repo"
    repo.mkdir(parents=True)
    (repo / "package.json").write_text(
        '{"scripts":{"test":"jest"},"devDependencies":{"jest":"^30"}}',
        encoding="utf-8",
    )
    (repo / "yarn.lock").write_text("", encoding="utf-8")
    verifier = tmp_path / "verifier"
    verifier.mkdir()
    (verifier / "verifier.test.tsx").write_text("", encoding="utf-8")
    (verifier / "manifest.json").write_text(
        '{"functional_artifact":"verifier.test.tsx"}', encoding="utf-8"
    )
    plan = execution_plan(tmp_path, {"repo_language": "typescript"}, "f2p")
    assert "yarn test --runInBand --runTestsByPath /app/verifier/verifier.test.tsx" in plan.command
    assert "node /app/verifier/verifier.test.tsx" not in plan.command


def test_jest_does_not_require_external_tsx_loader(tmp_path: Path) -> None:
    repo = tmp_path / "public" / "repo"
    repo.mkdir(parents=True)
    (repo / "package.json").write_text(
        '{"scripts":{"test":"jest --extensions .ts,.tsx"},"devDependencies":{"jest":"^27"}}',
        encoding="utf-8",
    )
    metadata = {"repo_language": "js"}
    spec = discover_execution_spec(repo, metadata)
    assert spec.runner_family == "jest"
    assert spec.typescript_loader == "tsx"
    plan = execution_plan(tmp_path, metadata, "p2p")
    assert "--loader none" in plan.command


def test_node_selector_runner_batches_cases_per_file() -> None:
    runner = Path("src/verifier_trans/deterministic/execution/node_p2p_runner.js").read_text()
    assert "Starting Jest/Vitest once per test case" in runner
    assert "uniqueTitles.map(escapeRegExp).join('|')" in runner
    assert ".replace(/\\s*\\|\\s*/g, ' ')" in runner
    assert "P2P execution mismatch: executed=" in runner


def test_execution_spec_discovers_python_and_go_metadata(tmp_path: Path) -> None:
    python_repo = tmp_path / "python"; python_repo.mkdir()
    (python_repo / "pyproject.toml").write_text("[project.optional-dependencies]\ntest=['pytest']\n", encoding="utf-8")
    assert discover_execution_spec(python_repo, {"repo_language": "python"}).runner_family == "pytest"
    go_repo = tmp_path / "go"; go_repo.mkdir()
    (go_repo / "go.mod").write_text("module example\n", encoding="utf-8")
    go_spec = discover_execution_spec(go_repo, {"repo_language": "go"})
    assert go_spec.runner_family == "go-test" and go_spec.supported


def test_unknown_native_runner_is_explicitly_unsupported(tmp_path: Path) -> None:
    repo = tmp_path / "public" / "repo"
    repo.mkdir(parents=True)
    (repo / "package.json").write_text('{"scripts":{"test":"custom-runner"}}', encoding="utf-8")
    spec = discover_execution_spec(repo, {"repo_language": "javascript"})
    assert spec.supported is False
    assert spec.runner_family == "unknown"


def test_legacy_package_metadata_keeps_native_default() -> None:
    plan = package_execution_plan({"repo_language": "javascript"}, "functional_f2p.js")
    assert plan is not None
    assert plan.spec is not None and plan.spec.runner_family == "mocha"
    assert "--runner mocha" in plan.selector_command


def test_execution_spec_discovers_nested_node_package_root(tmp_path: Path) -> None:
    repo = tmp_path / "repo" / "packages" / "client"
    repo.mkdir(parents=True)
    (repo / "package.json").write_text(
        '{"scripts":{"test":"jest"},"devDependencies":{"jest":"^30"}}', encoding="utf-8"
    )
    spec = discover_execution_spec(tmp_path / "repo", {"repo_language": "typescript"})
    assert spec.runner_family == "jest"
    assert spec.cwd == "packages/client"
    assert spec.module_root == "packages/client"


def test_execution_spec_discovers_project_owned_ospec_harness(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "test").mkdir(parents=True)
    (repo / "package.json").write_text(
        '{"scripts":{"testapi":"cd test && node test api"},"devDependencies":{"ospec":"^4"}}',
        encoding="utf-8",
    )
    (repo / "test" / "test.js").write_text("", encoding="utf-8")
    (repo / "test" / "TestBuilder.js").write_text("", encoding="utf-8")
    spec = discover_execution_spec(repo, {"repo_language": "typescript"})
    assert spec.runner_family == "ospec"
    assert spec.selector_style == "native-project-harness"
    assert spec.supported


def test_ospec_runner_is_supported_by_framework_source() -> None:
    runner = Path("src/verifier_trans/deterministic/execution/node_p2p_runner.js").read_text()
    assert "runOspecHarness" in runner
    assert "'test', 'test.js'" in runner
    assert "runOspecHarness(appDir, byFile, env)" in runner
    assert "path.join(appDir, 'test')" in runner


def test_manifest_target_is_mounted_and_used_by_native_functional_runner(tmp_path: Path) -> None:
    repo = tmp_path / "public" / "repo"
    repo.mkdir(parents=True)
    (repo / "package.json").write_text(
        '{"scripts":{"test":"jest"},"devDependencies":{"jest":"^30"}}',
        encoding="utf-8",
    )
    (repo / "yarn.lock").write_text("", encoding="utf-8")
    verifier = tmp_path / "verifier"
    verifier.mkdir()
    source = verifier / "generated.tsx"
    source.write_text("", encoding="utf-8")
    (verifier / "manifest.json").write_text(json.dumps({
        "functional_artifact": "generated.tsx",
        "test_files": [{"source": "generated.tsx", "target": "test/verifier-test.tsx"}],
    }), encoding="utf-8")
    plan = execution_plan(tmp_path, {"repo_language": "typescript"}, "f2p")
    assert "/app/test/verifier-test.tsx" in plan.command
    assert plan.mounts == ((source, "/app/test/verifier-test.tsx"),)
    assert "/app/verifier/generated.tsx" not in plan.command


def test_jest_verifier_namespace_target_expands_native_roots(tmp_path: Path) -> None:
    repo = tmp_path / "public" / "repo"
    repo.mkdir(parents=True)
    (repo / "package.json").write_text(
        '{"scripts":{"test":"jest"},"devDependencies":{"jest":"^30"}}',
        encoding="utf-8",
    )
    (repo / "yarn.lock").write_text("", encoding="utf-8")
    verifier = tmp_path / "verifier"
    verifier.mkdir()
    (verifier / "verifier.test.tsx").write_text("", encoding="utf-8")
    (verifier / "manifest.json").write_text(json.dumps({
        "functional_artifact": "verifier.test.tsx",
        "test_files": [{"source": "verifier.test.tsx", "target": "verifier/verifier.test.tsx"}],
    }), encoding="utf-8")
    plan = execution_plan(tmp_path, {"repo_language": "typescript"}, "f2p")
    assert "--roots /app" in plan.command
    assert "--testMatch '**/*.[jt]s?(x)'" in plan.command
    assert plan.command.endswith("--runTestsByPath /app/verifier/verifier.test.tsx")
