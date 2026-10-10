# Framework issue: descriptive functional verifier name fell back to run.sh

- UTC: 2026-09-22T22:55:44Z
- Instance: `instance_tutao__tutanota-4b4e45949096bb288f2b522f657610e480efa3e8`
- Attempt: `attempt_014`, core revision 1

## Phenomenon

Semantic Judge passed the TypeScript verifier, and deterministic replay was
stable and runnable, but both Base and Gold F2P failed. The replay log showed:

`/app/verifier/run.sh: line 5: cd: app: No such file or directory`

The verifier artifact was named `functional_xss_verifier.cjs`. The execution
adapter did not discover it and fell back to the compatibility `run.sh`, whose
relative `app/` assumption is not valid when replay starts at `/app`.

## Classification and root cause

This is a generic artifact/execution-adapter discovery and mount/cwd contract
failure, not a TypeScript semantic failure. `_functional_file()` only matched
the historical `functional_f2p.*` filename, despite the artifact contract
allowing equivalent descriptive functional test names.

## General fix

The deterministic execution adapter now discovers any regular artifact file
with the stable `functional_` prefix and dispatches it through the native
language adapter. It therefore executes `functional_xss_verifier.cjs` directly
with Node and avoids the legacy run.sh fallback. No repository, commit, or
test-name special case was added.

## Regression

Added an execution-adapter regression for
`functional_xss_verifier.cjs`. Targeted adapter tests passed (`13 passed`), and
the full suite passed (`101 passed`). A fresh TypeScript attempt is required to
validate the fix through Base/Gold replay.

