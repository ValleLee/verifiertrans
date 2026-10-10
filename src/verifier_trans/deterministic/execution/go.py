"""Go execution adapter."""

from __future__ import annotations

from pathlib import Path
import shlex


def functional_command(relative_name: str, spec=None, target_name: str | None = None) -> str:
    cwd = getattr(spec, "cwd", ".") or "."
    declared = target_name or relative_name
    artifact = shlex.quote(f"/app/{declared}")
    if Path(declared).suffix.lower() in {".sh", ".bash"}:
        command = f"bash {artifact}"
    else:
        command = f"go test {artifact}"
    return (
        f"cd /app/{cwd} && VERIFIER_REPO_ROOT=/app "
        f"VERIFIER_ARTIFACT_ROOT=/app/verifier VERIFIER_CWD=/app/{cwd} "
        f"{command}"
    )


def selector_command(selector_path: str, group: str, spec=None) -> str:
    cwd = getattr(spec, "cwd", ".") or "."
    return f"cd /app/{cwd} && python3 /framework/go_p2p_runner.py {selector_path} --group {group}"


def package_selector_command(selector_path: str, group: str, spec=None) -> str:
    cwd = getattr(spec, "cwd", ".") or "."
    return f"cd /app/{cwd} && python3 /tests/go_p2p_runner.py {selector_path} --group {group}"


def package_runner_source() -> Path:
    return Path(__file__).resolve().parent / "go_p2p_runner.py"


def runner_mounts(source_dir: Path) -> tuple[tuple[Path, str], ...]:
    return ((source_dir / "go_p2p_runner.py", "/framework/go_p2p_runner.py"),)
