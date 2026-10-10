# Framework Repair: Judge JSON Extraction

- Time: 2026-09-24
- Scope: shared semantic/candidate judge response parsing
- Trigger: element-web semantic judge responses repeatedly raised `JSONDecodeError` (`Extra data` / malformed-prefix) after the provider returned prose/fenced or multiple JSON objects. The controller correctly classified this as infrastructure, but the parser could not recover a valid verdict object.

## Evidence

- Existing `src/verifier_trans/agents/judge.py::_parse_json` selected the first `{` through the last `}`, which makes a valid response with a trailing JSON object fail with `Extra data`.
- The same path is shared by verifier semantic, positive adjudication, and negative adjudication judges; no task-specific behavior is involved.
- Existing infra retry remains authoritative when no unambiguous verdict object is present.

## Minimal repair

- Decode complete JSON objects with `JSONDecoder.raw_decode` at each object boundary.
- When wrapped output contains one or more objects, prefer the last object containing `verdict`; accept a single object without `verdict` for backward compatibility; reject ambiguous multi-object output without a verdict.
- Preserve the original raw response and usage accounting.

## Deterministic verification

- `tests/unit/test_judge_response_fallback.py`: wrapped prose/fenced response and multiple verdict objects.
- Result: 3 passed.

## Boundary audit

This repair changes only provider-response normalization shared by all judge roles. It adds no instance, repository, test-title, language, or verifier-filename special case.

## Follow-up evidence

During the first retry after the parser change, the provider returned multiple valid objects without a top-level `verdict`. The parser now recovers only a schema-shaped object containing one of the semantic judge fields (`findings`, `unconverted_f2p`, `overreach`, `mapping_gaps`); arbitrary multi-object output remains an infrastructure error. The deterministic suite is now 4 passed.
