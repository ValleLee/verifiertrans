"""Shared artifact helpers."""
from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from pathlib import Path
from typing import Any


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def copy_tree(source: Path, target: Path) -> None:
    """Copy an artifact tree while honoring the project's compatibility links.

    ``AttemptLayout`` exposes the writable verifier through a symlink such as
    ``.compat/verifier -> converter/current``.  Passing that link directly to
    ``shutil.copytree`` makes Python treat the existing link as a conflicting
    destination and raises ``FileExistsError`` at Converter submission time.
    Resolve directory symlinks before copying so the logical compatibility
    view and the classified artifact tree remain the same filesystem object.
    """
    if target.is_symlink():
        resolved = target.resolve(strict=False)
        if resolved.is_dir():
            target = resolved
        else:
            target.unlink()
    if target.exists():
        if not target.is_dir():
            target.unlink()
        else:
            shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        source,
        target,
        symlinks=True,
        ignore_dangling_symlinks=True,
        dirs_exist_ok=True,
    )


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    if path.is_file():
        digest.update(path.read_bytes())
    elif path.is_dir():
        for item in sorted(path.rglob("*")):
            if item.is_file():
                digest.update(str(item.relative_to(path)).encode())
                digest.update(item.read_bytes())
    return "sha256:" + digest.hexdigest()


def load_optional_json(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def publish_final_task(workspace: Path, revision: int) -> Path:
    """Atomically publish a smoke-tested package outside intermediate evidence."""
    from ..paths import RunLayout, attempt_from_path, utc_now

    attempt = attempt_from_path(workspace)
    metadata = json.loads((attempt.prepare / "metadata.json").read_text(encoding="utf-8"))
    run = RunLayout(attempt.root.parents[2], str(metadata["instance_id"]))
    candidate = attempt.packaging / "candidate_task"
    if not candidate.is_dir():
        raise FileNotFoundError(f"packaged task is missing: {candidate}")

    temporary = run.root / f".final_task.{uuid.uuid4().hex}.tmp"
    backup = run.root / f".final_task.{uuid.uuid4().hex}.previous"
    copy_tree(candidate, temporary)
    save_json(
        temporary / "provenance.json",
        {
            "schema_version": "1.0",
            "source_instance_id": metadata["instance_id"],
            "source_attempt": attempt.root.name,
            "verifier_revision": revision,
            "verifier_hash": file_digest(attempt.converter / "current"),
            "environment_hash": file_digest(candidate / "environment"),
            "published_at_utc": utc_now(),
        },
    )
    if run.final_task.exists():
        run.final_task.rename(backup)
    try:
        temporary.rename(run.final_task)
    except Exception:
        if backup.exists() and not run.final_task.exists():
            backup.rename(run.final_task)
        raise
    if backup.exists():
        shutil.rmtree(backup)
    return run.final_task
