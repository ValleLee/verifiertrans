"""Deterministic structural checks for Positive QA candidates."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


DIFF_HEADER = re.compile(r"^diff --git a/(.+) b/(.+)$")


def _safe_relative(value: str) -> str | None:
    path = Path(value.strip())
    if path.is_absolute() or ".." in path.parts:
        return None
    return path.as_posix()


def _gold_paths(patch: str) -> set[str]:
    paths: set[str] = set()
    for line in patch.splitlines():
        match = DIFF_HEADER.match(line)
        if not match:
            continue
        for raw in match.groups():
            relative = _safe_relative(raw)
            if relative:
                paths.add(relative)
    return paths


def _candidate_paths(candidate: Path) -> set[str]:
    result: set[str] = set()
    for path in candidate.rglob("*"):
        if not path.is_file() or path.name == "NOTES.md":
            continue
        relative = _safe_relative(str(path.relative_to(candidate)))
        if relative:
            result.add(relative)
    return result


def _read(path: Path) -> bytes | None:
    return path.read_bytes() if path.is_file() else None


def structural_precheck(workspace: Path, candidate: Path) -> dict[str, Any]:
    """Detect an exact Gold post-image reproduction before LLM adjudication.

    The check is intentionally narrow: it rejects only a candidate whose
    complete payload is exactly the Gold post-image over exactly the Gold's
    changed paths.  Same-file but genuinely different implementations remain
    eligible for the Positive Judge, which compares implementation structure
    and behavior with the supplied Gold reference.
    """
    patch_path = workspace / "sealed" / "gold.patch"
    base = workspace / "public" / "repo"
    if not patch_path.is_file() or not base.is_dir() or not candidate.is_dir():
        return {"status": "SKIP", "exact_gold_reproduction": False, "reason": "comparison_inputs_unavailable"}
    patch = patch_path.read_text(encoding="utf-8", errors="replace")
    gold_paths = _gold_paths(patch)
    candidate_paths = _candidate_paths(candidate)
    if not gold_paths:
        return {"status": "SKIP", "exact_gold_reproduction": False, "reason": "gold_patch_has_no_file_headers"}

    # Apply the reference patch to only the files it touches. This avoids
    # copying a potentially large repository while preserving git's hunk
    # semantics and rename/new-file behavior.
    try:
        with tempfile.TemporaryDirectory(prefix="verifier-positive-") as raw:
            root = Path(raw)
            for relative in gold_paths:
                source = base / relative
                if source.is_file():
                    target = root / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
            patch_file = root / "gold.patch"
            patch_file.write_text(patch, encoding="utf-8")
            applied = subprocess.run(
                ["git", "apply", "--whitespace=nowarn", str(patch_file)],
                cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, check=False,
            )
            if applied.returncode != 0:
                return {
                    "status": "SKIP", "exact_gold_reproduction": False,
                    "reason": "gold_patch_replay_unavailable",
                    "gold_paths": sorted(gold_paths),
                    "detail": applied.stdout[-1000:],
                }
            exact = candidate_paths == gold_paths and all(
                _read(candidate / relative) == _read(root / relative)
                for relative in gold_paths
            )
    except OSError as exc:
        return {"status": "SKIP", "exact_gold_reproduction": False, "reason": repr(exc)}

    return {
        "status": "FAIL" if exact else "PASS",
        "exact_gold_reproduction": exact,
        "gold_paths": sorted(gold_paths),
        "candidate_paths": sorted(candidate_paths),
        "non_gold_candidate_paths": sorted(candidate_paths - gold_paths),
    }
