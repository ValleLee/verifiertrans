# Framework fix: stale repair packet caused false QA defect

- UTC: 2026-09-22T16:01:40Z
- Discovered during: qutebrowser attempt_002, rev_3 QA
- Scope: generic orchestrator state machine

## Phenomenon

qutebrowser rev_3 passed Semantic Judge, Hard Validator, and Positive QA. The accepted Positive evidence was written, but the attempt terminated with `QA_DEFECT` before Negative QA, package smoke, or final_task. `control/state.json` reported `QA_DEFECT` while `qa/evidence.json` already contained one valid Positive.

## Root cause

rev_1 had an artifact sanity failure and populated the Converter `packet` with a repair diagnosis. After rev_2/rev_3 passed sanity, the packet was not cleared. The QA phase only checks whether `packet` is truthy after Positive generation, so the stale rev_1 diagnosis falsely converted a successful Positive into `QA_DEFECT`.

## Generic fix

Clear `packet` immediately after the current revision passes deterministic sanity. A repair packet now remains active only when the current revision actually fails a gate or receives new semantic/core/evidence failure.

## Tests

- Added a regression test asserting successful sanity clears the prior repair packet before Semantic Judge.
- Full framework pytest suite: 85 passed.
- Existing rev_3 semantic/core/Positive artifacts remain reusable; resume should continue with Negative QA without another Converter call.
