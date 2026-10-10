# Step 1: repository-native ExecutionSpec

- UTC: 2026-09-22T10:15:00Z
- Stage: A / execution adapter
- Scope: deterministic framework only; no fresh task and no model/API call.

## Change

Added `deterministic/execution/discovery.py` and made replay/candidate/package plans carry the
same immutable `ExecutionSpec`. The spec discovers package manager, runner family, selector
style, cwd/module root, TypeScript loader, declared Redis use, and explicit support status from
repository metadata. Python, Node/TypeScript and Go now have deterministic discovery paths;
unknown Node runners and missing Go module metadata are reported as unsupported infrastructure
rather than silently presented as supported.

The framework-owned Node runner now accepts Mocha, Jest and Vitest families and loader metadata.
Prepare preflight records the discovered spec and checks native Node runner binaries/collection
or Go module test collection instead of marking every non-Python check `SKIPPED`. The Converter
still emits only verifier semantics and does not receive Docker, selector-parser, or service
responsibility.

## Verification

- `tests/unit/test_execution_adapters.py`: 5 passed.
- `python -m compileall -q src tests`: passed.
- Existing execution-plan API and Mocha command contract remain compatible.

This is a generic adapter change; no repository, test name, or instance-specific branch was
added. Real Docker validation remains deferred to the explicitly excluded Step 5.
