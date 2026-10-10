"""Validate paths used by generated functional-verifier source files.

The Converter writes files under ``verifier/`` while deterministic replay runs
them from the fixed container layout ``/app/verifier`` with the repository at
``/app``.  A relative import that escapes that layout is an artifact defect,
not a semantic test failure.  Catch it before Docker replay so the failure
domain remains actionable and the Converter can repair it.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Any


SOURCE_SUFFIXES = {
    ".c", ".cc", ".cpp", ".cjs", ".go", ".java", ".js", ".mjs",
    ".py", ".rb", ".rs", ".sh", ".ts", ".tsx",
}

LOCAL_IMPORT = re.compile(
    r"(?:\bfrom\s*|\bimport\s+(?:[^\"']+\s+from\s+)?|\bimport\s*\(\s*|\brequire\s*\(\s*|\bsource\s+)"
    r"[\"'](?P<path>[^\"']+)[\"']"
)


def _candidate_paths(path: Path) -> list[Path]:
    if path.suffix:
        return [path]
    return [
        path,
        *(path.with_suffix(suffix) for suffix in (".js", ".mjs", ".cjs", ".ts", ".tsx", ".py", ".json")),
        *(path / f"index{suffix}" for suffix in (".js", ".mjs", ".cjs", ".ts", ".tsx", ".py")),
    ]


def _resolve_runtime_path(
    specifier: str, source: PurePosixPath, verifier: Path, repo: Path,
) -> tuple[str, bool]:
    if specifier.startswith("/"):
        target = PurePosixPath(specifier)
    else:
        target = PurePosixPath(source.parent, specifier)
        # PurePosixPath preserves ``..``; resolve it without touching the host.
        target = PurePosixPath("/") / target.relative_to(PurePosixPath("/"))
        parts: list[str] = []
        for part in target.parts:
            if part in ("", "/", "."):
                continue
            if part == "..":
                if parts:
                    parts.pop()
                else:
                    return f"outside_execution_root:{specifier}", False
            else:
                parts.append(part)
        target = PurePosixPath("/") / PurePosixPath(*parts)

    roots = (
        (PurePosixPath("/app/verifier"), verifier),
        (PurePosixPath("/app"), repo),
        (PurePosixPath("/workspace/verifier"), verifier),
        (PurePosixPath("/workspace/app"), repo),
        (PurePosixPath("/verifier"), verifier),
    )
    for runtime_root, host_root in roots:
        try:
            relative = target.relative_to(runtime_root)
        except ValueError:
            continue
        host_target = host_root.joinpath(*relative.parts)
        if any(candidate.is_file() for candidate in _candidate_paths(host_target)):
            return "", True
        return f"missing_target:{specifier}", False
    return f"outside_execution_root:{specifier}", False


def validate_artifact_paths(workspace: Path) -> dict[str, Any]:
    """Check static local imports against the canonical Docker layout."""
    verifier = workspace / "verifier"
    repo = workspace / "public" / "repo"
    issues: list[dict[str, str]] = []
    scanned = 0
    if not verifier.is_dir() or not repo.is_dir():
        return {"status": "SKIP", "scanned_files": 0, "issues": [], "reason": "workspace roots unavailable"}

    for source_path in sorted(verifier.iterdir()):
        if not source_path.is_file() or source_path.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        scanned += 1
        relative = source_path.relative_to(verifier).as_posix()
        runtime_source = PurePosixPath("/app/verifier") / relative
        text = source_path.read_text(encoding="utf-8", errors="replace")
        for match in LOCAL_IMPORT.finditer(text):
            specifier = match.group("path")
            if not (specifier.startswith(".") or specifier.startswith("/")):
                continue
            reason, ok = _resolve_runtime_path(specifier, runtime_source, verifier, repo)
            if not ok:
                issues.append({"file": relative, "specifier": specifier, "reason": reason})
    return {
        "status": "PASS" if not issues else "FAIL",
        "scanned_files": scanned,
        "issues": issues,
        "runtime_contract": {
            "repository_root": "/app",
            "artifact_root": "/app/verifier",
            "role_aliases": ["/workspace/app", "/workspace/verifier", "/verifier"],
        },
    }
