# Framework issue: Semantic Judge lacked source-to-resolved selector context

- UTC timestamp: 2026-09-22T23:30:53Z
- Scope: TypeScript/Tutanota attempt_014, Semantic Judge rev2

## Symptom

After the artifact contract repair, Sanity rev2 passed and the artifact
contained a real `verifier.py`. Semantic Judge rev2 still requested repair
because the trace used canonical resolved ids such as
`test/client/common/HtmlSanitizerTest.ts::test suite`, while the historical
seed used the dataset spelling
`test/tests/misc/HtmlSanitizerTest.js | test suite`.

## Root cause

Preparation deliberately normalizes historical selectors into executable
canonical ids, and deterministic sanity/replay validate against that resolved
list. The Semantic Judge evidence exposed the raw historical source list but
not the corresponding resolved list. Its prompt therefore implicitly treated
the raw spelling as the artifact accounting key, contradicting the existing
generic selector-accounting contract.

## Impact

The Judge misclassified a valid source-to-resolved normalization as missing
F2P traceability and consumed a Converter repair cycle. This was a generic
model-evidence contract defect, not a Tutanota-specific semantic requirement.

## General fix

`run_verifier_judge` now supplies both `fail_to_pass_source` and
`fail_to_pass_resolved`. The Semantic Judge prompt explicitly accepts a
one-to-one source-to-resolved normalization and requires artifact ids to match
the deterministic resolved contract, while still checking intent preservation.

## Tests

- Added a regression assertion for the dual source/resolved evidence fields.
- Full test suite will be run before resuming the current attempt.
- No task-specific selector mapping or verifier assertion was added.
