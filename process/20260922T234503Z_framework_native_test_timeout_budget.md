# Framework issue: native TypeScript F2P replay exceeded the verifier timeout

- UTC timestamp: 2026-09-22T23:45:03Z
- Scope: TypeScript/Tutanota attempt_014, core rev2 stability replay

## Symptom

The repaired artifact passed Sanity and Semantic Judge. Base F2P failed as
expected, Gold F2P passed in the first stability round, and both Base/Gold P2P
passed. A subsequent Gold F2P replay exceeded the configured 120-second
verifier timeout while the repository's native TypeScript build/test harness
was still running, so the core result was classified as infrastructure.

## Root cause

The execution adapter correctly selected the repository-native npm/ospec
runner, but the generic Hard Validator budget was shorter than the cold-build
time of this TypeScript repository. The budget was not language-aware and
treated a slow but runnable native test as a timeout failure.

## Impact

The verifier semantics and Docker mounts were not implicated. Stability could
not be established, and the controller would stop before QA even though the
first complete replay had the required Base/Gold/P2P outcomes.

## General fix

Raised `experiment.verifier_timeout_seconds` from 120 to 300 seconds. This is
still bounded by the existing QA/package budgets and applies uniformly to
native replay; it does not special-case Tutanota or alter the Converter's
artifact semantics.

## Tests and follow-up

- Full framework suite before this config-only change: `103 passed`.
- Reuse the current artifact and rerun core stability with the new budget.
- If the native runner remains above 300 seconds, record the measured phase
  and improve execution-spec budgeting generically rather than adding a task
  exception.
