"""Build conversion reports from immutable pipeline artifacts.

Reporting is deterministic: it does not call a model and only summarizes
structured evidence already produced by the pipeline.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def _json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default
    except (OSError, json.JSONDecodeError):
        return default


def _attempt_root(workspace: Path) -> Path:
    path = Path(workspace).resolve()
    if path.name == ".compat":
        return path.parent
    if (path / ".compat").is_dir():
        return path
    return path


def _run_root(attempt: Path) -> Path:
    if attempt.parent.name == "attempts" and attempt.parent.parent.name == "intermediate":
        return attempt.parents[2]
    return attempt


def _read_events(attempt: Path) -> list[dict[str, Any]]:
    path = attempt / "control/events.jsonl"
    if not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            events.append(value)
    return events


def _timestamp(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _timing(events: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [(event, stamp) for event in events if (stamp := _timestamp(event.get("time"))) is not None]
    if not valid:
        return {"observed_wall_seconds": None, "stage_seconds": {}}
    first, last = valid[0][1], valid[-1][1]
    stage_seconds: defaultdict[str, float] = defaultdict(float)
    for (event, start), (_, end) in zip(valid, valid[1:]):
        stage_seconds[str(event.get("state", "UNKNOWN"))] += max(0.0, (end - start).total_seconds())
    return {
        "first_event_utc": first.isoformat(),
        "last_event_utc": last.isoformat(),
        "observed_wall_seconds": round(max(0.0, (last - first).total_seconds()), 3),
        "stage_seconds": {key: round(value, 3) for key, value in stage_seconds.items()},
        "active_seconds_unavailable": True,
    }


def _normalise_usage(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    prompt_details = value.get("prompt_tokens_details") or {}
    cached = value.get("cached_tokens") or value.get("cache_read_input_tokens") or value.get("prompt_cache_hit_tokens")
    if not cached and isinstance(prompt_details, dict):
        cached = prompt_details.get("cached_tokens", 0)
    try:
        input_tokens = int(value.get("input_tokens") or value.get("prompt_tokens") or 0)
        output_tokens = int(value.get("output_tokens") or value.get("completion_tokens") or 0)
        total_tokens = int(value.get("total_tokens") or input_tokens + output_tokens)
        cached_tokens = int(cached or 0)
    except (TypeError, ValueError):
        return {}
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "cached_tokens": cached_tokens,
    }


def _add_usage(total: dict[str, int], usage: dict[str, int]) -> None:
    for key in ("input_tokens", "output_tokens", "total_tokens", "cached_tokens"):
        total[key] = total.get(key, 0) + int(usage.get(key, 0))


def _walk_usage(value: Any) -> Iterable[dict[str, int]]:
    if isinstance(value, dict):
        for key in ("usage", "model_usage"):
            if isinstance(value.get(key), dict):
                usage = _normalise_usage(value[key])
                if usage:
                    yield usage
        for child in value.values():
            yield from _walk_usage(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_usage(child)


def _model_usage(attempt: Path) -> dict[str, Any]:
    by_role: defaultdict[str, dict[str, int]] = defaultdict(
        lambda: {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cached_tokens": 0}
    )
    files = list(sorted((attempt / "converter/trajectories").glob("*.json")))
    files += list(sorted((attempt / "validation/semantic").glob("*.json")))
    files += list(sorted((attempt / "qa").glob("**/judge.json")))
    calls = 0
    for path in files:
        value = _json(path, {})
        if not isinstance(value, dict):
            continue
        text = str(path).lower()
        if path.name.lower().startswith("converter_"):
            role = "converter"
        elif path.name.lower().startswith("positive_"):
            role = "positive_generator"
        elif path.name.lower().startswith("mutant_"):
            role = "negative_generator"
        elif path.name == "judge.json" and "positive" in text:
            role = "positive_judge"
        elif path.name == "judge.json" and ("negative" in text or "mutation" in text):
            role = "negative_judge"
        elif "semantic" in text:
            role = "semantic_judge"
        else:
            role = "model"
        usages = list(_walk_usage(value))
        for usage in usages:
            _add_usage(by_role[role], usage)
            calls += 1
        stats = value.get("info", {}).get("model_stats", {})
        if not usages and isinstance(stats, dict):
            by_role[role]["api_calls"] = by_role[role].get("api_calls", 0) + int(stats.get("api_calls") or 0)
    total = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cached_tokens": 0}
    for value in by_role.values():
        _add_usage(total, value)
    return {
        "calls_with_usage": calls,
        "by_role": dict(by_role),
        "total": total,
        "cost": None,
        "cost_note": "Provider cost was not exposed by the configured API client." if calls else "unavailable",
    }


def _scope_trace(attempt: Path) -> dict[str, Any]:
    value = _json(attempt / "converter/current/instruction_scope_trace.json")
    if isinstance(value, dict):
        return value
    return {
        "schema_version": "1.0",
        "status": "UNAVAILABLE",
        "reason": "Converter did not emit instruction_scope_trace.json for this attempt.",
    }


def _source_counts(attempt: Path, trace: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    seeds = _json(attempt / "source/restricted/test_seeds.json", {}) or {}
    source_f2p = seeds.get("fail_to_pass_source", []) if isinstance(seeds, dict) else []
    source_p2p = seeds.get("pass_to_pass_source", []) if isinstance(seeds, dict) else []
    mappings = trace.get("f2p_mappings", []) if isinstance(trace, dict) else []
    decisions = Counter(str(row.get("decision", "unknown")) for row in mappings if isinstance(row, dict))
    emitted = sum(len(row.get("emitted_functional_tests", [])) for row in mappings if isinstance(row, dict))
    return {
        "source_f2p_count": len(source_f2p),
        "source_p2p_count": len(source_p2p),
        "mapped_f2p_count": len(mappings),
        "emitted_functional_test_count": emitted,
        "decisions": dict(decisions),
        "manifest_f2p_count": len(manifest.get("source_f2p_coverage", [])) if isinstance(manifest, dict) else None,
        "manifest_p2p_count": len(manifest.get("source_p2p_coverage", [])) if isinstance(manifest, dict) else None,
    }


def generate_report(workspace: Path) -> tuple[dict[str, Any], str]:
    attempt = _attempt_root(workspace)
    run = _run_root(attempt)
    events = _read_events(attempt)
    control_report = _json(attempt / "control/report.json", {}) or {}
    final = _json(attempt / "control/final.json", {}) or {}
    evidence = _json(attempt / "qa/evidence.json", {}) or {}
    trace = _json(attempt / "converter/current/conversion_trace.json", {}) or {}
    manifest = _json(attempt / "converter/current/manifest.json", {}) or {}
    metadata = _json(attempt / "prepare/metadata.json", {}) or {}
    revision = final.get("revision")
    status = control_report.get("status") or ("VERIFIED" if final.get("accepted") else "IN_PROGRESS")
    current_state = events[-1].get("state", "UNKNOWN") if events else "NEW"
    counts = _source_counts(attempt, trace, manifest)
    metrics = {
        "schema_version": "1.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "instance_id": metadata.get("instance_id", run.name),
        "attempt": attempt.name,
        "status": status,
        "state": current_state,
        "revision": revision,
        "counts": counts,
        "timing": _timing(events),
        "model_usage": _model_usage(attempt),
        "attempts": {
            "events": len(events),
            "states": dict(Counter(str(event.get("state", "UNKNOWN")) for event in events)),
            "converter_revisions": len(list((attempt / "converter/trajectories").glob("converter_rev_*.json"))),
            "semantic_judge_files": len(list((attempt / "validation/semantic").glob("rev_*.json"))),
            "hard_replay_files": len(list((attempt / "validation/hard_replay").glob("rev_*.json"))),
            "positive_candidates": len(evidence.get("positives", [])) if isinstance(evidence, dict) else 0,
            "negative_candidates": len(evidence.get("mutants", [])) if isinstance(evidence, dict) else 0,
        },
        "validation": {
            "final": final,
            "semantic": _json(attempt / "validation/semantic" / f"rev_{int(revision):03d}.json") if isinstance(revision, int) else None,
            "hard_replay": _json(attempt / "validation/hard_replay" / f"rev_{int(revision):03d}.json") if isinstance(revision, int) else None,
        },
        "artifacts": {"attempt": str(attempt), "final_task": str(run / "final_task") if (run / "final_task").is_dir() else None},
    }
    review = run / "review"
    review.mkdir(parents=True, exist_ok=True)
    (review / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (review / "instruction_scope_trace.json").write_text(json.dumps(_scope_trace(attempt), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    mappings = trace.get("f2p_mappings", []) if isinstance(trace, dict) else []
    with (review / "f2p_mapping.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=[
            "source_test_id", "original_intent", "relevant_evidence", "binding_found",
            "observable_surface", "decision", "emitted_functional_tests", "brief_rationale",
        ])
        writer.writeheader()
        for row in mappings:
            if isinstance(row, dict):
                writer.writerow({
                    key: "; ".join(value) if isinstance(value, list) else value
                    for key, value in ((field, row.get(field, "")) for field in writer.fieldnames)
                })
    report = _render_markdown(attempt, metrics, trace, evidence)
    (review / "conversion_report.md").write_text(report, encoding="utf-8")
    return metrics, report


def _md(value: Any) -> str:
    if value is None:
        return "null"
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def _render_markdown(attempt: Path, metrics: dict[str, Any], trace: dict[str, Any], evidence: dict[str, Any]) -> str:
    counts = metrics["counts"]
    final = metrics["validation"]["final"] or {}
    hard = metrics["validation"].get("hard_replay") or {}
    semantic = metrics["validation"].get("semantic") or {}
    source_statement = attempt / "source/public/problem_statement.md"
    instruction = attempt / "converter/current/instruction_scope.md"
    rows = trace.get("f2p_mappings", []) if isinstance(trace, dict) else []
    lines = [
        "# Functional Verifier Conversion Report", "",
        f"- Instance: `{metrics['instance_id']}`",
        f"- Attempt: `{metrics['attempt']}`",
        f"- Status: **{metrics['status']}** / `{metrics['state']}`",
        f"- Final revision: `{metrics.get('revision')}`", "",
        "## 1. Executive summary", "",
        f"- Historical F2P: **{counts['source_f2p_count']}**; mapped: **{counts['mapped_f2p_count']}**; emitted functional tests: **{counts['emitted_functional_test_count']}**.",
        f"- Historical P2P: **{counts['source_p2p_count']}**.",
        f"- Decisions: `{json.dumps(counts['decisions'], ensure_ascii=False)}`.",
        f"- Positive QA: **{len(evidence.get('positives', [])) if isinstance(evidence, dict) else 0}**; Negative QA: **{len(evidence.get('mutants', [])) if isinstance(evidence, dict) else 0}**.",
        f"- Observed wall time: **{metrics['timing'].get('observed_wall_seconds')} seconds**; active time is not available from legacy events.",
        f"- Model tokens: **{metrics['model_usage']['total']['total_tokens']}** total, **{metrics['model_usage']['total']['input_tokens']}** input, **{metrics['model_usage']['total']['output_tokens']}** output.", "",
        "## 2. Problem Statement → instruction scope", "",
        f"Original source: `{source_statement}`", f"Final scope: `{instruction}`", "",
        "The final instruction is derived from F2P-supported semantics plus the necessary public contract. Behavior described in the Problem Statement without an F2P seed is outside this conversion scope unless explicitly marked as a necessary public contract.", "",
        "### Original Problem Statement", "", "<details><summary>展开原始 Problem Statement</summary>", "",
        source_statement.read_text(encoding="utf-8") if source_statement.is_file() else "(unavailable)", "", "</details>", "",
        "### Final instruction scope", "",
        instruction.read_text(encoding="utf-8") if instruction.is_file() else "(unavailable)", "",
        "## 3. F2P conversion mapping", "",
        "| Source F2P | Original intent | Binding | Observable surface | Decision | Emitted tests |",
        "|---|---|---|---|---|---|",
    ]
    for row in rows:
        if isinstance(row, dict):
            lines.append("| " + " | ".join([
                _md(row.get("source_test_id")), _md(row.get("original_intent")), _md(row.get("binding_found")),
                _md(row.get("observable_surface")), _md(row.get("decision")),
                _md("; ".join(row.get("emitted_functional_tests", []))),
            ]) + " |")
    if not rows:
        lines.append("| (conversion trace unavailable) | | | | | |")
    lines.extend([
        "", "## 4. Validation evidence", "", "| Gate | Result |", "|---|---|",
        f"| Semantic Judge | `{_md(semantic.get('verdict') or semantic.get('status') or 'unavailable')}` |",
        f"| Base + converted F2P | `{_md((hard.get('base_f2p') or {}).get('passed'))}` |",
        f"| Gold + converted F2P | `{_md((hard.get('gold_f2p') or {}).get('passed'))}` |",
        f"| Base + P2P | `{_md((hard.get('base_p2p') or {}).get('passed'))}` |",
        f"| Gold + P2P | `{_md((hard.get('gold_p2p') or {}).get('passed'))}` |",
        f"| Stable replay | `{_md(hard.get('stable'))}` |", f"| Final accepted | `{_md(final.get('accepted'))}` |", "",
        "## 5. QA evidence", "",
        "Positive and Negative candidate details are retained in `intermediate/attempts/.../qa/` and summarized in `qa/evidence.json`. This report records verdicts and reasons, not hidden model chain-of-thought.", "",
    ])
    for category, key in (("Positive", "positives"), ("Negative", "mutants")):
        lines.append(f"### {category} candidates")
        items = evidence.get(key, []) if isinstance(evidence, dict) else []
        if not items:
            lines.append("- None recorded.")
        for item in items:
            judge = item.get("judge", {}) if isinstance(item, dict) else {}
            lines.append(f"- `{item.get('name')}`: `{judge.get('verdict', 'unknown')}` — {_md('; '.join(judge.get('reasons', [])))}")
        lines.append("")
    lines.extend([
        "## 6. Attempts, cost, and reproducibility", "", "```json",
        json.dumps({"attempts": metrics["attempts"], "timing": metrics["timing"], "model_usage": metrics["model_usage"]}, ensure_ascii=False, indent=2),
        "```", "", "The machine-readable source of truth is `review/metrics.json`; regenerate with `verifier-trans report`.", "",
    ])
    return "\n".join(lines)


def write_report(workspace: Path) -> dict[str, Any]:
    metrics, _ = generate_report(workspace)
    return metrics


def write_progress(workspace: Path) -> None:
    """Write a cheap live progress view after every controller event."""
    attempt = _attempt_root(workspace)
    run = _run_root(attempt)
    events = _read_events(attempt)
    if not events:
        return
    review = run / "review"
    review.mkdir(parents=True, exist_ok=True)
    state = events[-1].get("state", "UNKNOWN")
    value = {
        "schema_version": "1.0", "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "instance_id": (_json(attempt / "prepare/metadata.json", {}) or {}).get("instance_id", run.name),
        "attempt": attempt.name, "state": state, "last_node": events[-1].get("node"),
        "event_count": len(events), "state_counts": dict(Counter(str(event.get("state", "UNKNOWN")) for event in events)),
        "last_event": events[-1],
    }
    (review / "progress.json").write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (review / "progress.md").write_text(
        "# Conversion progress\n\n" + f"- State: **{state}**\n" + f"- Last node: `{value['last_node']}`\n" +
        f"- Events: `{value['event_count']}`\n" + f"- Updated: `{value['updated_at_utc']}`\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--workspace", type=Path)
    source.add_argument("--instance-id")
    parser.add_argument("--runs-root", type=Path)
    args = parser.parse_args()
    if args.workspace:
        workspace = args.workspace
    else:
        from ...paths import DEFAULT_RUNS_ROOT, RunLayout
        workspace = RunLayout.for_instance(args.runs_root or DEFAULT_RUNS_ROOT, args.instance_id).latest_attempt().root
    metrics = write_report(workspace)
    print(json.dumps({"status": "OK", "instance_id": metrics.get("instance_id"), "review": str(_run_root(_attempt_root(workspace)) / "review")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
