# Framework issue: run.sh-only conversion artifact accepted before execution

- UTC timestamp: 2026-09-22T23:22:11Z
- Scope: TypeScript/Tutanota attempt_014, revision 1

## Symptom

The Converter artifact passed the Semantic Judge, but `verifier/` contained
only `run.sh` and audit metadata. There was no functional verifier source
file. The deterministic execution adapter therefore fell back to `run.sh`.
That script resolved the repository as `.../cd .. && cd app`, which produced
`/app/app` inside the replay container and failed before the repository test
runner started.

## Root cause

The artifact sanity validator checked that `run.sh` existed, but did not
require the semantic test source promised by the Converter contract. A
run.sh-only artifact could therefore reach Semantic Judge and Hard Validator;
the eventual path failure was then reported as a verifier execution/semantic
failure instead of an artifact-schema failure.

## Impact

This was a general cross-language handoff defect, not a Tutanota-specific
requirement. It allowed the Converter to mix test meaning and runtime
plumbing, obscured the execution-adapter boundary, and consumed a repair/API
cycle on an artifact that was incomplete before replay.

## General fix

`validate_verifier` now requires at least one top-level executable/source
artifact with a supported source suffix, excluding the audit files and the
compatibility `run.sh`. The failure is deterministic:
`missing_functional_verifier_source` with `failure_class=ARTIFACT_SCHEMA`.
`run.sh` remains available as a thin compatibility entrypoint, while the
Hard Validator remains responsible for language-specific execution, mounts,
cwd, services, and P2P selection.

## Tests

- Targeted regression: `26 passed`.
- Added coverage proving a run.sh-only artifact is rejected.
- Existing execution-adapter and MiniSWE snapshot/recovery tests remain green.

## Follow-up

Attempt_014 should be resumed through the existing Converter repair path after
the deterministic contract is active. No task-specific filename or behavior
was added to the framework.
