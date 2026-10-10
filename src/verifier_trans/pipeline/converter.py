"""Converter mode definitions.

The same Converter implementation is used for initial BUILD and evidence-led
REPAIR; there is deliberately no separate design agent.
"""
from enum import StrEnum
from pathlib import Path
from typing import Any


class ConverterMode(StrEnum):
    BUILD = "BUILD"
    REPAIR = "REPAIR"


SUBMIT_SENTINEL = "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"


def terminal_submission(result: str) -> bool:
    return SUBMIT_SENTINEL in result


def session_step_cap(
    config: dict[str, Any], role: str, *, repair: bool = False
) -> int:
    """Return an emergency tool-step ceiling, never a revision budget."""
    if role == "converter":
        key = "repair_step_cap" if repair else "converter_step_cap"
        legacy = "repair_turns" if repair else "converter_turns"
        default = 120 if repair else 160
    elif role == "mutator":
        key, legacy, default = "mutation_step_cap", "mutation_turns", 100
    else:
        key, legacy, default = "solver_step_cap", "solver_turns", 100
    return int(config["agent"].get(key, config["agent"].get(legacy, default)))


def self_review_passed(workspace: Path) -> bool:
    path = workspace / "verifier" / "self_review.md"
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8", errors="replace").upper()
    return "SELF_REVIEW: PASS" in text or text.rstrip().endswith("PASS")
