"""State and failure-domain definitions used by the orchestrator."""
from __future__ import annotations

from enum import StrEnum
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .artifacts import save_json


class FailureClass(StrEnum):
    NONE = "NONE"
    ARTIFACT_SCHEMA = "ARTIFACT_SCHEMA"
    INFRASTRUCTURE = "INFRASTRUCTURE"
    VERIFIER_SEMANTIC = "VERIFIER_SEMANTIC"
    QA_DEFECT = "QA_DEFECT"
    PACKAGE = "PACKAGE"


class PipelineState(StrEnum):
    NEW = "NEW"
    PREPARED = "PREPARED"
    CONVERTING = "CONVERTING"
    SEMANTIC_VALIDATING = "SEMANTIC_VALIDATING"
    HARD_VALIDATING = "HARD_VALIDATING"
    QA = "QA"
    REPAIR = "REPAIR"
    FINAL_VALIDATED = "FINAL_VALIDATED"
    PACKAGED = "PACKAGED"
    MANUAL_REVIEW = "MANUAL_REVIEW"


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_event(workspace: Path, state: str, node: str, **extra: Any) -> None:
    event = {"time": utc(), "state": state, "node": node, **extra}
    path = workspace / "events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        import json

        stream.write(json.dumps(event, ensure_ascii=False) + "\n")
    save_json(
        workspace / "state.json",
        {"state": state, "last_node": node, "updated_at_utc": event["time"], **extra},
    )
    # Keep a cheap live progress view available while long model/Docker stages
    # are running. Reporting is observability only and must never break the
    # conversion itself.
    try:
        from ..deterministic.reporting.report import write_progress
        write_progress(workspace)
    except Exception:
        pass


def infra_failure(check: dict[str, Any]) -> bool:
    if (
        check.get("failure_class") == FailureClass.INFRASTRUCTURE
        or check.get("failure_domain") == "infrastructure"
    ):
        return True
    infra = {
        "docker_unavailable",
        "toolchain_missing",
        "timeout",
        "setup_failed",
        "patch_failed",
        "no_marker",
    }
    return any(
        (check.get(key) or {}).get("failure_cause") in infra
        for key in ("base_f2p", "gold_f2p", "base_p2p", "gold_p2p")
    )
