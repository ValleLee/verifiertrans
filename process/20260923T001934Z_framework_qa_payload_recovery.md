# Framework issue: QA payload existed before solver submission sentinel

- UTC timestamp: 2026-09-23T00:19:34Z
- Scope: TypeScript/Tutanota attempt_014 Positive QA

## Symptom

The Positive solver session was interrupted while waiting on a slow model/tool
cycle and did not emit `COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT`. It had already
written a candidate payload at `qa/candidates/positive_1_attempt_1/src/misc/HtmlSanitizer.ts`.
The controller treated the missing sentinel as a fatal generation error and
did not run deterministic precheck on the existing payload.

## Root cause

QA generation required the model-level sentinel before exposing any candidate
to the deterministic replay layer. There was no artifact handoff path for a
complete payload surviving an interrupted session.

## Impact

An independently usable candidate could be discarded, causing another model
request and wasting API budget. This is separate from candidate semantic
validity and does not change the verifier or core gate.

## General fix

`generate_solver` now preserves a non-empty existing candidate directory and
returns it to deterministic precheck even if the model session did not emit
the sentinel. It still raises when neither a sentinel nor any payload exists;
no completion signal is fabricated and no candidate bypasses replay/Judge.

## Tests

- Targeted orchestrator/MiniSWE regression: `10 passed`.
- The existing TypeScript candidate payload is retained for deterministic
  precheck on the next resume.
