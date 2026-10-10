"""Python execution adapter."""

from __future__ import annotations

from pathlib import Path
import shlex


def functional_command(relative_name: str, spec=None, target_name: str | None = None) -> str:
    cwd = getattr(spec, "cwd", ".") or "."
    declared = target_name or relative_name
    artifact = shlex.quote(f"/app/{declared}")
    interpreter = "bash" if Path(declared).suffix.lower() in {".sh", ".bash"} else "python3"
    return (
        f"cd /app/{cwd} && VERIFIER_REPO_ROOT=/app "
        f"VERIFIER_ARTIFACT_ROOT=/app/verifier VERIFIER_CWD=/app/{cwd} "
        f"{interpreter} {artifact}"
    )


def selector_command(selector_path: str, group: str, spec=None) -> str:
    cwd = getattr(spec, "cwd", ".") or "."
    return f"cd /app/{cwd} && python3 /framework/p2p_runner.py {selector_path} --group {group}"


def package_selector_command(selector_path: str, group: str, spec=None) -> str:
    cwd = getattr(spec, "cwd", ".") or "."
    return f"cd /app/{cwd} && python3 /tests/p2p_runner.py {selector_path} --group {group}"


def package_runner_source() -> Path:
    return Path(__file__).resolve().parents[1] / "replay" / "p2p_runner.py"


def runner_mounts(source_dir: Path) -> tuple[tuple[Path, str], ...]:
    # The Python runner remains framework-owned, but lives beside the replay
    # implementation rather than in the language adapter directory.
    runner = Path(__file__).resolve().parents[1] / "replay" / "p2p_runner.py"
    return ((runner, "/framework/p2p_runner.py"),)
