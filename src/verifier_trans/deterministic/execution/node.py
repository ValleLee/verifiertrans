"""Node.js execution adapter.

The adapter selects the repository's native Mocha/Jest/Vitest/ospec toolchain
inside the image. Selector interpretation lives in the framework-owned Node
helper, not in a model-generated verifier file.
"""

from __future__ import annotations

from pathlib import Path
import shlex
from .discovery import ExecutionSpec


def functional_command(
    relative_name: str, spec: ExecutionSpec | None = None, target_name: str | None = None,
) -> str:
    spec = spec or ExecutionSpec("node", "mocha", "npm", ".", ".", "file-and-grep", (), None, True, "default")
    cwd = spec.cwd or "."
    artifact = shlex.quote(f"/app/{target_name}" if target_name else f"/app/verifier/{relative_name}")
    env = (
        f"VERIFIER_REPO_ROOT=/app VERIFIER_ARTIFACT_ROOT=/app/verifier "
        f"VERIFIER_CWD=/app/{cwd}"
    )
    if Path(target_name or relative_name).suffix.lower() in {".sh", ".bash"}:
        return f"cd /app/{cwd} && {env} bash {artifact}"
    # Jest/Vitest must be launched through the repository-native runner so
    # TypeScript/TSX transforms and project configuration remain authoritative.
    # Direct Node execution is retained only for runners whose contract is an
    # executable artifact (the historical Mocha/ospec compatibility path).
    if spec.runner_family == "jest":
        # A manifest may intentionally place the generated artifact in the
        # framework-owned ``verifier/`` namespace.  Repository Jest configs
        # commonly restrict ``roots`` to ``test/``; keep the explicit target
        # authoritative while allowing Jest to resolve that declared file.
        roots = (
            " --roots /app --testMatch '**/*.[jt]s?(x)'"
            if target_name and target_name.split("/", 1)[0] == "verifier"
            else ""
        )
        args = f"--runInBand{roots} --runTestsByPath {artifact}"
    elif spec.runner_family == "vitest":
        args = f"run {artifact}"
    else:
        return f"cd /app/{cwd} && {env} node {artifact}"
    manager = spec.package_manager or "npm"
    if manager == "npm":
        command = f"npm test -- {args}"
    else:
        command = f"{manager} test {args}"
    return f"cd /app/{cwd} && {env} {command}"


def selector_command(selector_path: str, group: str, spec: ExecutionSpec | None = None) -> str:
    spec = spec or ExecutionSpec("node", "mocha", "npm", ".", ".", "file-and-grep", (), None, True, "default")
    # Jest/Vitest load TS/TSX through their repository configuration.  Inject
    # tsx/ts-node only for runners that actually need a Node loader (currently
    # Mocha); otherwise a metadata hint such as a `.tsx` extension can make a
    # valid image fail with `Cannot find package 'tsx'`.
    loader = spec.typescript_loader if spec.runner_family == "mocha" else None
    return f"cd /app/{spec.cwd} && node /framework/node_p2p_runner.js {selector_path} --group {group} --runner {spec.runner_family} --loader {loader or 'none'} --cwd /app/{spec.cwd}"


def package_selector_command(selector_path: str, group: str, spec: ExecutionSpec | None = None) -> str:
    spec = spec or ExecutionSpec("node", "mocha", "npm", ".", ".", "file-and-grep", (), None, True, "default")
    loader = spec.typescript_loader if spec.runner_family == "mocha" else None
    return f"cd /app/{spec.cwd} && node /tests/node_p2p_runner.js {selector_path} --group {group} --runner {spec.runner_family} --loader {loader or 'none'} --cwd /app/{spec.cwd}"


def package_runner_source() -> Path:
    return Path(__file__).resolve().parent / "node_p2p_runner.js"


def runner_mounts(source_dir: Path) -> tuple[tuple[Path, str], ...]:
    return ((source_dir / "node_p2p_runner.js", "/framework/node_p2p_runner.js"),)
