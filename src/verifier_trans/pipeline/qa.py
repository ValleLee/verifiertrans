"""Verifier-QA role definitions."""
from enum import StrEnum
import json
from pathlib import Path
from typing import Any

from .artifacts import save_json


class QAKind(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"


POSITIVE_CONTRACT_VERSION = 5
NEGATIVE_CONTRACT_VERSION = 1


def positive_candidate_contract(
    p2p: dict[str, Any],
    f2p: dict[str, Any],
    historical: dict[str, Any],
    structural: dict[str, Any],
) -> dict[str, Any]:
    """Classify the deterministic evidence before semantic adjudication.

    A candidate positive is eligible for semantic adjudication when it is
    runnable on the retained P2P contract and on the converted F2P contract.
    The converted F2P result is deliberately *not* a validity gate here: a
    runnable semantic failure is exactly the evidence needed to discover a
    verifier false negative.  Historical F2P remains audit-only.
    """
    p2p_runnable = p2p.get("runnable") is True
    f2p_runnable = f2p.get("runnable") is True
    p2p_pass = p2p.get("accepted") is True
    current_pass = f2p.get("accepted") is True
    infrastructure = candidate_infra_failure(p2p) or candidate_infra_failure(f2p)
    structurally_distinct = not structural.get("exact_gold_reproduction", False)
    eligible = (
        p2p_runnable and f2p_runnable and p2p_pass
        and structurally_distinct and not infrastructure
    )
    return {
        "status": "candidate_positive" if eligible else "not_candidate_positive",
        "eligible_for_adjudication": eligible,
        "p2p_runnable": p2p_runnable,
        "current_f2p_runnable": f2p_runnable,
        "p2p_pass": p2p_pass,
        "current_f2p_pass": current_pass,
        "current_f2p_failure_is_semantic": (
            eligible and not current_pass and not infrastructure
        ),
        "historical_f2p_runnable": historical.get("runnable") is True,
        "structurally_distinct": structurally_distinct,
        "failure_class": "INFRASTRUCTURE" if infrastructure else "NONE",
    }


def validated_positive_contract(
    judge_valid: bool,
    p2p: dict[str, Any],
    f2p: dict[str, Any],
    historical: dict[str, Any],
) -> dict[str, Any]:
    """Separate semantic validation from current-verifier acceptance.

    ``hard_false_negative`` is raised only after the Solution Judge has
    validated the candidate and the current F2P replay is a runnable semantic
    failure.  Infrastructure failures never cause a verifier repair.
    """
    p2p_pass = p2p.get("accepted") is True
    current_pass = f2p.get("accepted") is True
    current_runnable = f2p.get("runnable") is True
    current_infra = candidate_infra_failure(p2p) or candidate_infra_failure(f2p)
    hard_false_negative = bool(
        judge_valid and p2p_pass and current_runnable and not current_pass and not current_infra
    )
    return {
        "status": "validated_positive" if judge_valid else "candidate_positive",
        "judge_valid": judge_valid,
        "p2p_pass": p2p_pass,
        "current_f2p_pass": current_pass,
        "historical_f2p_runnable": historical.get("runnable") is True,
        "hard_false_negative": hard_false_negative,
        "accepted": bool(judge_valid and p2p_pass and current_pass),
        "failure_class": "INFRASTRUCTURE" if current_infra else "NONE",
    }


def positive_execution_contract(p2p: dict[str, Any], f2p: dict[str, Any], historical: dict[str, Any]) -> dict[str, Any]:
    """Require current success; retain historical replay as audit evidence.

    Historical F2P is deliberately not a validity gate.  A functional
    Positive may pass, fail, or be unable to run the inherited test suite;
    only the current converted F2P and retained P2P contracts decide whether
    the candidate is accepted.
    """
    current_pass = f2p.get("accepted") is True
    p2p_pass = p2p.get("accepted") is True
    historical_runnable = historical.get("runnable") is True
    historical_pass = historical.get("accepted") is True if historical_runnable else None
    current_infra = candidate_infra_failure(p2p) or candidate_infra_failure(f2p)
    legacy_separation = historical_runnable and historical_pass is False
    return {
        "contract_version": POSITIVE_CONTRACT_VERSION,
        "accepted": p2p_pass and current_pass,
        "p2p_pass": p2p_pass,
        "current_f2p_pass": current_pass,
        "historical_f2p_runnable": historical_runnable,
        "historical_f2p_pass": historical_pass,
        "legacy_f2p_separation": legacy_separation,
        "historical_f2p_infrastructure": (not historical_runnable and candidate_infra_failure(historical)),
        "failure_class": "INFRASTRUCTURE" if current_infra else "NONE",
    }


def negative_execution_contract(
    judged_relevant: bool, p2p: dict[str, Any], f2p: dict[str, Any]
) -> dict[str, Any]:
    """Classify one qualified mutant without conflating infra and semantics."""
    p2p_pass = p2p.get("accepted") is True
    f2p_pass = f2p.get("accepted") is True
    infrastructure = candidate_infra_failure(p2p) or candidate_infra_failure(f2p)
    rejected = bool(judged_relevant and p2p_pass and not f2p_pass and not infrastructure)
    false_positive = bool(judged_relevant and p2p_pass and f2p_pass and not infrastructure)
    return {
        "contract_version": NEGATIVE_CONTRACT_VERSION,
        "judged_relevant": bool(judged_relevant),
        "p2p_pass": p2p_pass,
        "current_f2p_pass": f2p_pass,
        "accepted": rejected,
        "false_positive": false_positive,
        "failure_class": "INFRASTRUCTURE" if infrastructure else "NONE",
        "repair_required": false_positive,
        "infrastructure_failure": infrastructure,
    }


def candidate_infra_failure(candidate: dict[str, Any]) -> bool:
    if candidate.get("failure_class") == "INFRASTRUCTURE":
        return True
    return candidate.get("failure_cause") in {
        "timeout",
        "setup_failed",
        "apply_failed",
        "no_marker",
        "toolchain_missing",
        "docker_unavailable",
        "environment_missing",
    }


def candidate_files(path: Path, limit: int = 160_000) -> dict[str, str]:
    result: dict[str, str] = {}
    used = 0
    for item in sorted(path.rglob("*")):
        if not item.is_file() or item.name == "NOTES.md":
            continue
        text = item.read_text(encoding="utf-8", errors="replace")
        result[str(item.relative_to(path))] = text[: max(0, limit - used)]
        used += len(text)
        if used >= limit:
            break
    return result


def load_evidence(workspace: Path) -> dict[str, Any]:
    path = workspace / "evidence.json"
    if not path.is_file():
        return {
            "positives": [], "mutants": [],
            "candidate_positives": [], "validated_positives": [],
        }
    evidence = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(evidence, dict):
        evidence.setdefault("candidate_positives", [])
        evidence.setdefault("validated_positives", [])
    return evidence


def save_evidence(workspace: Path, evidence: dict[str, Any]) -> None:
    save_json(workspace / "evidence.json", evidence)
