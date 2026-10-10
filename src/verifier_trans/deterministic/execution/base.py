"""Build a deterministic execution plan from task metadata and artifact files."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any
import re

from . import go, node, python
from .discovery import ExecutionSpec, discover_execution_spec


EXECUTION_CONTRACT_VERSION = "execution-adapter-v1"


def parse_result_marker(output: str, namespace: str, name: str) -> int | None:
    """Parse the contract's marker-v1 result format for any execution mode."""
    match = re.search(rf"^{re.escape(namespace)}_{re.escape(name)}=(\d+)$", str(output), re.MULTILINE)
    return int(match.group(1)) if match else None


@dataclass(frozen=True)
class ExecutionPlan:
    language: str
    group: str
    command: str
    mounts: tuple[tuple[Path, str], ...]
    adapter: str
    spec: ExecutionSpec | None = None


@dataclass(frozen=True)
class PackageExecutionPlan:
    language: str
    functional_command: str
    selector_command: str
    runner_source: Path
    runner_name: str
    spec: ExecutionSpec | None = None


def standard_role_mounts(workspace: Path, log_dir: Path) -> tuple[tuple[Path, str], ...]:
    """Canonical role mounts shared by deterministic replay entrypoints."""
    return (
        (workspace / "verifier", "/verifier"),
        (workspace / "verifier", "/app/verifier"),
        (workspace / "verifier", "/workspace/verifier"),
        (workspace / "sealed", "/sealed"),
        (workspace / "restricted" / "resolved_test_selectors.json", "/restricted/resolved_test_selectors.json"),
        (workspace / "restricted", "/workspace/restricted"),
        (log_dir, "/logs"),
    )


def contract_environment_args(spec: ExecutionSpec | None) -> tuple[str, ...]:
    """Render frozen environment entries as safe Docker ``-e`` arguments."""
    if spec is None:
        return ()
    result: list[str] = []
    for key, value in spec.environment:
        if not key or not key.replace("_", "").isalnum() or key[0].isdigit():
            raise ValueError(f"invalid execution environment key: {key!r}")
        result.extend(("-e", f"{key}={value}"))
    return tuple(result)


def normalize_language(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"javascript", "typescript", "node", "nodejs", "js", "ts"}:
        return "node"
    if text in {"python", "python3", "py"}:
        return "python"
    if text in {"golang", "go"}:
        return "go"
    return text or "unknown"


def _functional_file(verifier: Path) -> str | None:
    # Legacy reader used only by direct pre-Prepare compatibility callers.
    candidates = sorted(path for path in verifier.glob("functional_*") if path.is_file())
    if not candidates:
        return None
    return candidates[0].name


def _manifest_functional_file(verifier: Path, *, allow_legacy: bool = False) -> str | None:
    """Resolve the functional entrypoint from the manifest, never a scan."""
    manifest_path = verifier / "manifest.json"
    if not manifest_path.is_file():
        return _functional_file(verifier) if allow_legacy else None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    declared = manifest.get("functional_artifact") or manifest.get("functional_entrypoint")
    if isinstance(declared, dict):
        declared = declared.get("source") or declared.get("path") or declared.get("name")
    name = str(declared or "").strip()
    if not name or Path(name).is_absolute() or ".." in Path(name).parts:
        return None
    return name if (verifier / name).is_file() else None


def _manifest_functional_target(verifier: Path, functional_name: str) -> str | None:
    """Return the manifest-declared repository target for the functional file."""
    manifest_path = verifier / "manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    declared = manifest.get("test_files")
    if not isinstance(declared, list):
        return None
    for item in declared:
        if not isinstance(item, dict) or str(item.get("source") or "") != functional_name:
            continue
        target = str(item.get("target") or "").strip()
        target_path = Path(target)
        if not target or target_path.is_absolute() or ".." in target_path.parts:
            return None
        return target
    return None


def execution_spec(workspace: Path, metadata: dict[str, Any]) -> ExecutionSpec:
    # Prepare is the only stage allowed to discover repository capabilities.
    # Replay and QA must consume the frozen serialized contract.  The
    # discovery fallback is retained only for pre-Prepare/unit-test callers.
    frozen = metadata.get("execution_spec")
    if isinstance(frozen, dict):
        return ExecutionSpec.from_dict(frozen)
    return discover_execution_spec(workspace / "public" / "repo", metadata)


def execution_plan(workspace: Path, metadata: dict[str, Any], group: str) -> ExecutionPlan:
    """Return the command and mounts for one deterministic replay group.

    `legacy_f2p` deliberately uses the original F2P selectors.  It is used by
    Positive QA to demonstrate that a structurally different valid solution is
    not merely reproducing the old test implementation.
    """

    allowed = {"f2p", "p2p", "legacy_f2p"}
    if group not in allowed:
        raise ValueError(f"unsupported execution group: {group}")
    language = normalize_language(metadata.get("repo_language"))
    frozen = metadata.get("execution_spec")
    spec = execution_spec(workspace, metadata)
    verifier = workspace / "verifier"
    source_dir = Path(__file__).resolve().parent
    if group == "f2p":
        name = _manifest_functional_file(verifier, allow_legacy=not isinstance(frozen, dict))
        if not name:
            raise ValueError("manifest must declare functional_artifact for f2p execution")
        target = _manifest_functional_target(verifier, name)
        artifact_mounts = (((verifier / name), f"/app/{target}"),) if target else ()
        if language == "node":
            return ExecutionPlan(language, group, node.functional_command(name, spec, target), artifact_mounts, "node", spec)
        if language == "python":
            return ExecutionPlan(language, group, python.functional_command(name, spec, target), artifact_mounts, "python", spec)
        if language == "go":
            return ExecutionPlan(language, group, go.functional_command(name, spec, target), artifact_mounts, "go", spec)
        raise ValueError(f"unsupported execution language for manifest functional artifact: {language}")

    selector_path = "/restricted/resolved_test_selectors.json"
    selector_group = "fail_to_pass" if group == "legacy_f2p" else "pass_to_pass"
    if language == "node":
        command = node.selector_command(selector_path, selector_group, spec)
        mounts = node.runner_mounts(source_dir)
        return ExecutionPlan(language, group, command, mounts, "node", spec)
    if language == "python":
        command = python.selector_command(selector_path, selector_group, spec)
        mounts = python.runner_mounts(source_dir)
        return ExecutionPlan(language, group, command, mounts, "python", spec)
    if language == "go":
        command = go.selector_command(selector_path, selector_group, spec)
        mounts = go.runner_mounts(source_dir)
        return ExecutionPlan(language, group, command, mounts, "go", spec)
    raise ValueError(f"unsupported execution language for selector replay: {language}")


def package_execution_plan(
    metadata: dict[str, Any], functional_name: str, functional_target: str | None = None,
) -> PackageExecutionPlan | None:
    """Build the package commands from the same language adapter as replay.

    Package containers place framework-owned runners under /tests rather than
    /framework, so only the container-local runner path changes.
    """
    language = normalize_language(metadata.get("repo_language"))
    raw_spec = metadata.get("execution_spec")
    # Old prepared attempts have no serialized spec. Preserve their previous
    # native defaults for package compatibility; fresh Prepare always writes a
    # discovered spec and never relies on this branch.
    if not isinstance(raw_spec, dict):
        # Legacy reader for direct callers only.  The package command itself
        # rejects attempts without Prepare's frozen spec before reaching here.
        if language == "node":
            spec = ExecutionSpec("node", "mocha", "npm", ".", ".", "file-and-grep", (), None, True, "legacy compatibility")
        elif language == "python":
            spec = ExecutionSpec("python", "pytest", "pip", ".", ".", "file-and-node", (), None, True, "legacy compatibility")
        elif language == "go":
            spec = ExecutionSpec("go", "go-test", "go", ".", ".", "package-and-test-name", (), None, True, "legacy compatibility")
        else:
            return None
    else:
        spec = ExecutionSpec.from_dict(raw_spec)
    if language == "node":
        return PackageExecutionPlan(
            language,
            node.functional_command(functional_name, spec, functional_target),
            node.package_selector_command("/tests/resolved_test_selectors.json", "pass_to_pass", spec),
            node.package_runner_source(),
            "node_p2p_runner.js", spec,
        )
    if language == "python":
        return PackageExecutionPlan(
            language,
            python.functional_command(functional_name, spec, functional_target),
            python.package_selector_command("/tests/resolved_test_selectors.json", "pass_to_pass", spec),
            python.package_runner_source(),
            "p2p_runner.py", spec,
        )
    if language == "go":
        return PackageExecutionPlan(
            language,
            go.functional_command(functional_name, spec, functional_target),
            go.package_selector_command("/tests/resolved_test_selectors.json", "pass_to_pass", spec),
            go.package_runner_source(),
            "go_p2p_runner.py", spec,
        )
    return None
