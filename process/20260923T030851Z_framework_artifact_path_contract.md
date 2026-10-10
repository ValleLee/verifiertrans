# Framework issue: generated artifact path contract

- UTC: 2026-09-23T03:08:51Z
- Scope: generic execution layer; discovered during the Tutanota TypeScript Step 5 conversion

## Phenomenon

Tutanota's submitted functional artifact was runnable as a Node process, but
Gold F2P failed during module resolution. A file mounted at
`/app/verifier/functional_tests.mjs` imported `../../src/...`, which resolves
to `/src/...` rather than the repository at `/app/src/...`. The old pipeline
classified this only after Docker replay as a verifier failure.

## Root cause

The CLI/controller and Docker mounts were already centralized, but the
artifact contract was implicit. Converter role paths (`/workspace/...`) and
replay paths (`/app/...`) were documented separately, and sanity validation
did not resolve local imports against the replay layout. A submitted artifact
could therefore pass schema and self-review while remaining unusable in the
actual Hard Validator container.

## Impact

The defect consumed a verifier repair revision and made a runtime path error
look like a semantic verifier failure. It can affect JavaScript/TypeScript
artifacts and any future generated source containing local runtime paths.

## General fix

1. Added a deterministic artifact path-contract check to sanity validation.
   It models `/app` as the repository root and `/app/verifier` as the artifact
   root, checks static local imports, rejects root-escaping paths, and rejects
   missing local targets before Semantic Judge and Hard Validator replay.
2. Functional execution adapters now run from the discovered repository cwd
   and export `VERIFIER_REPO_ROOT`, `VERIFIER_ARTIFACT_ROOT`, and
   `VERIFIER_CWD` for environment-rooted generated tests.
3. Updated the Converter contract prompt with the same runtime paths and the
   correct relative-import rule.

## Verification

- Targeted adapter, path-contract, and orchestrator tests: `22 passed`.
- The Tutanota attempt reached `HARD_VALIDATED` and `QA_POSITIVE` on rev3
  before this latest sanity gate was added; it must be resumed so the latest
  framework revision is exercised end to end.
- No instance-specific path workaround was added.

