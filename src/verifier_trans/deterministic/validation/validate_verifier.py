#!/usr/bin/env python3
"""Validate the final Converter artifacts and F2P accounting."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from .artifact_contract import ARTIFACT_SCHEMA_VERSION, add_contract
from .path_contract import validate_artifact_paths
from .instruction_policy import audit_instruction_scope


DECISIONS = {"keep", "rewrite", "merge", "drop", "spec_gap"}
TRACE_FIELDS = (
    "source_test_id", "original_intent", "relevant_evidence", "binding_found",
    "observable_surface", "decision", "emitted_functional_tests", "brief_rationale",
)

def extract_coverage_ids(value: Any, field: str, errors: list[str]) -> set[str]:
    """Read the canonical list-based source coverage from a manifest."""
    if not isinstance(value, list):
        errors.append(f"{field}_coverage_not_list")
        return set()
    normalized = [str(item).strip() for item in value]
    if any(not item for item in normalized):
        errors.append(f"{field}_coverage_contains_empty_id")
    duplicates = sorted({item for item in normalized if item and normalized.count(item) > 1})
    if duplicates:
        errors.append(f"{field}_coverage_duplicate_ids:" + ",".join(duplicates[:20]))
    return {item for item in normalized if item}


def read_json(path: Path, errors: list[str], error: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        errors.append(error)
        return {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--revision", type=int, default=1)
    args = parser.parse_args()
    root = args.workspace.resolve()
    verifier = root / "verifier"
    errors: list[str] = []

    required = {
        "manifest": verifier / "manifest.json",
        "run_sh": verifier / "run.sh",
        "conversion_log": verifier / "conversion_log.md",
        "conversion_trace": verifier / "conversion_trace.json",
        "coverage_matrix": verifier / "coverage_matrix.md",
        "self_review": verifier / "self_review.md",
        "instruction_scope": verifier / "instruction_scope.md",
    }
    for name, path in required.items():
        if not path.is_file():
            errors.append(f"missing_{name}")

    manifest = read_json(required["manifest"], errors, "invalid_manifest_json") \
        if required["manifest"].is_file() else {}
    if not isinstance(manifest, dict):
        errors.append("manifest_not_object")
        manifest = {}
    for key in ("f2p_command", "p2p_command"):
        if not str(manifest.get(key) or "").strip():
            errors.append(f"missing_manifest_{key}")
    if not manifest.get("functional_surfaces"):
        errors.append("missing_functional_surfaces")
    if manifest.get("schema_version") != ARTIFACT_SCHEMA_VERSION:
        errors.append("manifest_schema_version_mismatch")
    functional_artifact = str(manifest.get("functional_artifact") or "").strip()
    declared_items = manifest.get("test_files")
    declared_sources: set[str] = set()
    if (not functional_artifact or Path(functional_artifact).is_absolute()
            or ".." in Path(functional_artifact).parts):
        errors.append("missing_manifest_functional_artifact")
    if not isinstance(declared_items, list) or not declared_items:
        errors.append("missing_manifest_test_files")
        declared_items = []
    for index, item in enumerate(declared_items):
        if not isinstance(item, dict):
            errors.append(f"manifest_test_files_{index}_not_object")
            continue
        source = str(item.get("source") or "").strip()
        target = str(item.get("target") or "").strip()
        if (not source or Path(source).is_absolute() or ".." in Path(source).parts
                or not target or Path(target).is_absolute() or ".." in Path(target).parts):
            errors.append(f"manifest_test_files_{index}_invalid_path")
            continue
        if source in declared_sources:
            errors.append(f"manifest_test_files_duplicate_source:{source}")
        declared_sources.add(source)
        if not (verifier / source).is_file():
            errors.append(f"missing_manifest_artifact:{source}")
    if functional_artifact not in declared_sources or not (verifier / functional_artifact).is_file():
        errors.append("missing_functional_verifier_source")

    audit_files = {path.name for path in required.values()} | {"instruction_scope_trace.json"}
    for path in verifier.rglob("*") if verifier.is_dir() else ():
        if not path.is_file():
            continue
        relative = str(path.relative_to(verifier))
        if relative not in declared_sources and relative not in audit_files:
            errors.append(f"undeclared_verifier_file:{relative}")

    # Runtime plumbing is now supplied by Hard Validator's deterministic
    # execution adapter.  A Converter artifact may expose a thin compatibility
    # run.sh, but it must not smuggle a task-specific selector/P2P runner back
    # into the verifier package.
    if required["run_sh"].is_file():
        run_text = required["run_sh"].read_text(encoding="utf-8", errors="replace").lower()
        for marker in ("run_p2p", "p2p_runner", "selector_parser", "docker run", "pytest"):
            if marker in run_text:
                errors.append(f"run_sh_contains_runtime_plumbing:{marker}")
    for path in verifier.iterdir() if verifier.is_dir() else ():
        if path.is_file() and path.name.lower() in {"run_p2p.js", "run_p2p.py", "p2p_runner.js", "p2p_runner.py"}:
            errors.append(f"task_specific_runtime_file:{path.name}")

    selector_path = root / "restricted" / "resolved_test_selectors.json"
    if not selector_path.is_file():
        errors.append("missing_resolved_test_selectors")
    selectors = read_json(selector_path, errors, "invalid_resolved_test_selectors") \
        if selector_path.is_file() else {}
    expected_f2p = set((selectors.get("fail_to_pass") or {}).get("resolved") or []) \
        if isinstance(selectors, dict) else set()
    expected_p2p = set((selectors.get("pass_to_pass") or {}).get("resolved") or []) \
        if isinstance(selectors, dict) else set()

    coverage_ids = extract_coverage_ids(
        manifest.get("source_f2p_coverage"), "source_f2p", errors
    )
    missing = sorted(expected_f2p - coverage_ids)
    unexpected = sorted(coverage_ids - expected_f2p)
    if missing:
        errors.append("unaccounted_f2p:" + ",".join(missing[:20]))
    if unexpected:
        errors.append("unexpected_f2p_coverage:" + ",".join(unexpected[:20]))
    p2p_coverage_ids = extract_coverage_ids(
        manifest.get("source_p2p_coverage"), "source_p2p", errors
    )
    p2p_missing = sorted(expected_p2p - p2p_coverage_ids)
    p2p_unexpected = sorted(p2p_coverage_ids - expected_p2p)
    if p2p_missing:
        errors.append("unaccounted_p2p:" + ",".join(p2p_missing[:20]))
    if p2p_unexpected:
        errors.append("unexpected_p2p_coverage:" + ",".join(p2p_unexpected[:20]))

    trace_ids: set[str] = set()
    trace_path = required["conversion_trace"]
    if trace_path.is_file():
        trace = read_json(trace_path, errors, "invalid_conversion_trace_json")
        if isinstance(trace, dict) and trace.get("schema_version") != ARTIFACT_SCHEMA_VERSION:
            errors.append("conversion_trace_schema_version_mismatch")
        rows = trace.get("f2p_mappings") if isinstance(trace, dict) else None
        if not isinstance(rows, list):
            errors.append("conversion_trace_missing_f2p_mappings")
            rows = []
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                errors.append(f"trace_{index}_not_object")
                continue
            source_id = str(row.get("source_test_id") or "").strip()
            label = source_id or str(index)
            if not source_id or source_id in trace_ids:
                errors.append(f"trace_{index}_bad_source_test_id")
            trace_ids.add(source_id)
            for field in TRACE_FIELDS:
                if field not in row:
                    errors.append(f"trace_{label}_missing_{field}")
            if row.get("decision") not in DECISIONS:
                errors.append(f"trace_{label}_bad_decision")
            if row.get("decision") in {"keep", "rewrite", "merge"}:
                if not str(row.get("observable_surface") or "").strip():
                    errors.append(f"trace_{label}_missing_observable_surface")
                if not row.get("emitted_functional_tests"):
                    errors.append(f"trace_{label}_missing_emitted_tests")
            if not str(row.get("brief_rationale") or "").strip():
                errors.append(f"trace_{label}_missing_rationale")
        if trace_ids != expected_f2p:
            missing = sorted(expected_f2p - trace_ids)
            unexpected = sorted(trace_ids - expected_f2p)
            if missing:
                errors.append("trace_unaccounted_f2p:" + ",".join(missing[:20]))
            if unexpected:
                errors.append("trace_unexpected_f2p:" + ",".join(unexpected[:20]))
    if trace_ids != coverage_ids and coverage_ids:
        errors.append("manifest_trace_accounting_mismatch")

    scope_path = required["instruction_scope"]
    instruction_audit = audit_instruction_scope(scope_path)
    if instruction_audit.get("status") == "FAIL":
        errors.extend("instruction_binding:" + item for item in instruction_audit.get("hard_errors", []))
    if scope_path.is_file() and not scope_path.read_text(encoding="utf-8").rstrip().endswith(
        "INSTRUCTION_SCOPE: PASS"
    ):
        errors.append("instruction_scope_not_pass")
    review_path = required["self_review"]
    if review_path.is_file() and not review_path.read_text(encoding="utf-8").rstrip().endswith(
        "SELF_REVIEW: PASS"
    ):
        errors.append("self_review_not_pass")

    path_contract = validate_artifact_paths(root)
    if path_contract.get("status") == "FAIL":
        for issue in path_contract.get("issues", []):
            errors.append(
                "artifact_path_contract:" + ":".join(
                    str(issue.get(key) or "") for key in ("file", "specifier", "reason")
                )
            )

    payload = {
        "node": "verifier_sanity", "revision": args.revision,
        "node_status": "PASS" if not errors else "REPAIR", "errors": errors,
        "verifier": str(verifier),
        "run_sh_executable": bool(required["run_sh"].is_file() and os.access(required["run_sh"], os.X_OK)),
        "f2p_count": len(expected_f2p),
        "path_contract": path_contract,
        "instruction_audit": instruction_audit,
    }
    result = add_contract(root, args.revision, payload,
                          status="PASS" if not errors else "FAIL",
                          failure_class="NONE" if not errors else "ARTIFACT_SCHEMA")
    output = root / "artifacts" / "validation" / f"sanity_rev_{args.revision:03d}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
