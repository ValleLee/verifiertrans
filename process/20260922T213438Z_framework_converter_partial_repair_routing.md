# Framework issue: Converter step-limit failure discarded partial work

- UTC: 2026-09-22T21:34:38Z
- Instance: `instance_tutao__tutanota-4b4e45949096bb288f2b522f657610e480efa3e8-vee878bb72091875e912c52fc32bc60ec3760227b`
- Stage: TypeScript Step 5, `attempt_010`

## Phenomenon

The fresh Converter BUILD reached its configured 160-action ceiling after
writing `functional_tests.ts` but before writing the required audit files and
submission sentinel. The controller then started `converter_rev_2` with
`repair=false`, discarding the partial BUILD context and redoing repository
exploration. The run was stopped while the second BUILD was waiting on another
model response to avoid unnecessary API use.

## Root cause

The Converter exception handler recorded the failure but did not promote the
session-isolated staging directory into the next Converter context. Therefore
an incomplete artifact was indistinguishable from a fresh BUILD failure.

## Impact

- The same Converter could spend two full action budgets rediscovering a large
  TypeScript repository.
- Useful partial tests and the exact step-limit evidence were not available to
  the next revision.
- No Semantic Judge, Hard Validator, QA, or package result was produced for
  this attempt.

## General fix

`orchestrator.py` now detects a non-empty failed Converter staging directory,
promotes its filtered contents into the current verifier workspace, and creates
an evidence-led REPAIR packet containing the original error and partial-file
list. The next revision remains the same single Converter in REPAIR mode and
preserves valid work. If no partial staging exists, the old manual-review path
is retained.

## Test result

The full framework unit suite passed: `96 passed`. The interrupted model
session was stopped before another BUILD request; its exact trajectory and
attempt evidence remain under `attempt_010`.

