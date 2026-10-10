"""Shared metadata for revision-bound framework artifacts."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ARTIFACT_SCHEMA_VERSION = "3.0"
FAILURE_CLASSES = {
    "NONE", "ARTIFACT_SCHEMA", "INFRASTRUCTURE", "VERIFIER_SEMANTIC", "QA_DEFECT",
}


def verifier_hash(verifier: Path) -> str:
    digest = hashlib.sha256()
    if verifier.is_dir():
        for path in sorted(item for item in verifier.rglob("*") if item.is_file()):
            digest.update(str(path.relative_to(verifier)).encode("utf-8"))
            digest.update(path.read_bytes())
    return "sha256:" + digest.hexdigest()


def contract_fields(workspace: Path, revision: int, status: str,
                    failure_class: str = "NONE") -> dict[str, Any]:
    metadata_path = workspace / "run" / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.is_file() else {}
    if failure_class not in FAILURE_CLASSES:
        raise ValueError(f"unknown failure class: {failure_class}")
    return {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "instance_id": metadata.get("instance_id"),
        "verifier_revision": revision,
        "verifier_hash": verifier_hash(workspace / "verifier"),
        "status": status,
        "failure_class": failure_class,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def add_contract(workspace: Path, revision: int, payload: dict[str, Any],
                 *, status: str, failure_class: str = "NONE") -> dict[str, Any]:
    # Contract fields are authoritative.  A model-produced payload may contain
    # a coincidental ``status`` or stale revision; never let it shadow the
    # controller's binding metadata.
    result = dict(payload)
    result.update(contract_fields(workspace, revision, status, failure_class))
    return result
