"""Repository-native execution metadata discovery.

This module is deliberately deterministic and has no Docker or model calls.  It
reads the checked-out repository's conventional metadata and returns a small
description consumed by all execution adapters.  The description is evidence,
not a license to guess a runner when the repository does not declare one.
"""

from __future__ import annotations

import json
import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ExecutionSpec:
    language: str
    runner_family: str
    package_manager: str
    cwd: str
    module_root: str
    selector_style: str
    services: tuple[str, ...]
    typescript_loader: str | None
    supported: bool
    reason: str
    environment: tuple[tuple[str, str], ...] = ()
    # These values are part of the frozen execution contract.  They have
    # defaults so old source-level adapters remain readable, but a prepared
    # attempt serializes them and all later stages consume that serialization.
    timeout_seconds: int = 1800
    startup_timeout_seconds: int = 120
    kill_grace_seconds: int = 5
    result_parser: str = "marker-v1"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self) | {"services": list(self.services), "environment": [list(item) for item in self.environment]}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ExecutionSpec":
        """Deserialize the immutable Prepare contract without rediscovery."""
        if not isinstance(value, dict):
            raise ValueError("execution_spec must be an object")
        environment = tuple(
            (str(item[0]), str(item[1]))
            for item in value.get("environment") or ()
            if isinstance(item, (list, tuple)) and len(item) == 2
        )
        return cls(
            language=str(value.get("language") or "unknown"),
            runner_family=str(value.get("runner_family") or "unknown"),
            package_manager=str(value.get("package_manager") or "unknown"),
            cwd=str(value.get("cwd") or "."),
            module_root=str(value.get("module_root") or value.get("cwd") or "."),
            selector_style=str(value.get("selector_style") or "unsupported"),
            services=tuple(str(item) for item in value.get("services") or ()),
            typescript_loader=value.get("typescript_loader"),
            supported=bool(value.get("supported")),
            reason=str(value.get("reason") or "serialized Prepare contract"),
            environment=environment,
            timeout_seconds=int(value.get("timeout_seconds") or 1800),
            startup_timeout_seconds=int(value.get("startup_timeout_seconds") or 120),
            kill_grace_seconds=int(value.get("kill_grace_seconds") or 5),
            result_parser=str(value.get("result_parser") or "marker-v1"),
        )


def execution_spec_hash(spec: ExecutionSpec) -> str:
    """Return the stable identity attached to every stage result."""
    payload = json.dumps(spec.as_dict(), sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _node_spec(repo: Path, metadata: dict[str, Any], cwd: str = ".") -> ExecutionSpec:
    package = _load_json(repo / "package.json")
    scripts = package.get("scripts") if isinstance(package.get("scripts"), dict) else {}
    dependencies: dict[str, Any] = {}
    for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        value = package.get(key)
        if isinstance(value, dict):
            dependencies.update(value)
    text = " ".join(str(value) for value in scripts.values()) + " " + " ".join(dependencies)
    lowered = text.lower()
    if "jest" in lowered or "@jest/" in lowered:
        runner = "jest"
        selector = "file-and-test-name"
    elif "vitest" in lowered:
        runner = "vitest"
        selector = "file-and-test-name"
    elif "mocha" in lowered:
        runner = "mocha"
        selector = "file-and-grep"
    elif "ospec" in lowered or ((repo / "test" / "test.js").is_file() and (repo / "test" / "TestBuilder.js").is_file()):
        # Some TypeScript repositories use a project-owned ospec build/test
        # harness instead of a package-manager runner.  The presence of the
        # native harness is the deterministic capability signal.
        runner = "ospec"
        selector = "native-project-harness"
    else:
        runner = "unknown"
        selector = "unsupported"

    loader = None
    if any(token in lowered for token in ("ts-node", "ts-node/register")):
        loader = "ts-node/register"
    elif "tsx" in lowered:
        loader = "tsx"
    elif "typescript" in lowered or (repo / "tsconfig.json").is_file():
        loader = "repository-native"

    package_manager = "npm"
    if (repo / "pnpm-lock.yaml").is_file():
        package_manager = "pnpm"
    elif (repo / "yarn.lock").is_file():
        package_manager = "yarn"
    elif (repo / "package-lock.json").is_file():
        package_manager = "npm"
    supported = runner != "unknown"
    reason = "package.json declares a supported native test runner" if supported else "no supported runner in package metadata"
    if loader == "repository-native" and runner in {"jest", "vitest", "mocha", "ospec"}:
        reason += "; TypeScript loader must be provided by the repository runner"
    return ExecutionSpec(
        language="node", runner_family=runner, package_manager=package_manager,
        cwd=cwd, module_root=cwd, selector_style=selector,
        services=("redis",) if "redis" in lowered else (),
        typescript_loader=loader, supported=supported, reason=reason,
    )


def _python_spec(repo: Path) -> ExecutionSpec:
    candidates = [repo / "pyproject.toml", repo / "pytest.ini", repo / "tox.ini", repo / "setup.cfg"]
    text = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in candidates if path.is_file()).lower()
    if "pytest" in text or any(repo.glob("test*.py")) or any(repo.glob("tests/**/*.py")):
        return ExecutionSpec("python", "pytest", "pip", ".", ".", "file-and-node", (), None, True, "pytest metadata or test files found")
    return ExecutionSpec("python", "unittest", "pip", ".", ".", "file-and-node", (), None, True, "unittest fallback is repository-native")


def _go_spec(repo: Path) -> ExecutionSpec:
    if (repo / "go.mod").is_file():
        return ExecutionSpec("go", "go-test", "go", ".", ".", "package-and-test-name", (), None, True, "go.mod found")
    if (repo / "Makefile").is_file() and "go test" in repo.joinpath("Makefile").read_text(encoding="utf-8", errors="ignore"):
        return ExecutionSpec("go", "go-test", "go", ".", ".", "package-and-test-name", (), None, True, "Makefile declares go test")
    return ExecutionSpec("go", "unknown", "go", ".", ".", "unsupported", (), None, False, "go.mod and Makefile go test metadata missing")


def discover_execution_spec(repo: Path | None, metadata: dict[str, Any]) -> ExecutionSpec:
    """Discover one spec from a prepared repository, with explicit fallback.

    A missing repository is common in unit tests and during pre-prepare schema
    checks.  In that case the language-only fallback is marked unsupported for
    native selector execution; callers must not present it as cross-language
    support.
    """
    language = str(metadata.get("repo_language") or "").strip().lower()
    root = Path(repo) if repo is not None else Path()
    if language in {"javascript", "typescript", "node", "nodejs", "js", "ts"}:
        if not root.is_dir():
            return ExecutionSpec("node", "unknown", "npm", ".", ".", "unsupported", (), None, False, "repository is not materialized")
        manifests = [root / "package.json"] + sorted(
            path for path in root.glob("**/package.json")
            if path != root / "package.json" and len(path.relative_to(root).parts) <= 3
        )
        manifest = next((path for path in manifests if path.is_file()), None)
        package_root = manifest.parent if manifest else root
        cwd = str(package_root.relative_to(root)) if package_root != root else "."
        return _node_spec(package_root, metadata, cwd)
    if language in {"python", "python3", "py"}:
        return _python_spec(root) if root.is_dir() else ExecutionSpec("python", "pytest", "pip", ".", ".", "file-and-node", (), None, True, "language fallback before repository discovery")
    if language in {"go", "golang"}:
        if not root.is_dir():
            return ExecutionSpec("go", "unknown", "go", ".", ".", "unsupported", (), None, False, "repository is not materialized")
        manifests = [root / "go.mod"] + sorted(
            path for path in root.glob("**/go.mod")
            if path != root / "go.mod" and len(path.relative_to(root).parts) <= 3
        )
        module = next((path for path in manifests if path.is_file()), None)
        module_root = module.parent if module else root
        cwd = str(module_root.relative_to(root)) if module_root != root else "."
        spec = _go_spec(module_root)
        return ExecutionSpec(spec.language, spec.runner_family, spec.package_manager, cwd, cwd,
                             spec.selector_style, spec.services, spec.typescript_loader,
                             spec.supported, spec.reason, spec.environment)
    return ExecutionSpec(language or "unknown", "unknown", "unknown", ".", ".", "unsupported", (), None, False, "unsupported repository language")
