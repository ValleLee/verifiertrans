# Framework issue: typed manifest repair handoff

- Time (UTC): 2026-09-23T16:42:48+00:00
- Scope: generic Converter artifact repair contract
- Trigger: qutebrowser Round2 fresh attempt_001, revisions 1-3

## Evidence

Prepare and environment preflight passed. The Converter produced a valid observable F2P design and complete trace, but three consecutive submissions failed deterministic Sanity because `manifest.test_files` remained a list of bare strings and `functional_artifact` was not a declared source. The same failure repeated after automatic repair, so this was not a repository runtime or selector failure.

## Classification

`ARTIFACT` / generic Converter repair-contract weakness. The validator correctly rejected the artifact; no task-specific verifier or execution workaround is justified.

## Minimal framework change

- Clarified the canonical `{source, target}` object shape in `prompts/converter.md`.
- Extended `repair_packet()` to translate manifest schema errors into an explicit typed-artifact instruction while preserving accumulated evidence.
- Added a deterministic regression test in `tests/unit/test_orchestrator_state.py`.

The change does not normalize or silently accept malformed artifacts; Sanity remains authoritative.

## Verification

`tests/unit/test_orchestrator_state.py`: 8 passed. Full regression remains required before the next fresh attempt.

## Follow-up

Start a new fresh Prepare/attempt for qutebrowser after the regression suite. Do not reuse the rejected revision as accepted evidence.
