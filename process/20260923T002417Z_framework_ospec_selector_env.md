# Framework issue: ospec P2P runner referenced an undefined environment

- UTC timestamp: 2026-09-23T00:24:17Z
- Scope: TypeScript/Tutanota Positive QA legacy-F2P comparison

## Symptom

The candidate's legacy F2P comparison invoked the framework-owned Node ospec
selector runner and failed with `ReferenceError: env is not defined` before
the repository tests ran. The current functional F2P failure separately
showed the candidate replay uid issue.

## Root cause

`runOspecHarness(appDir, byFile)` used `env` in `spawnSync` but did not receive
the environment object that `main()` had constructed. This was a generic
execution-adapter bug affecting any Node/TypeScript repository using the
project-owned ospec harness with a non-empty selector group.

## Impact

P2P/legacy comparison results could be misclassified as candidate semantic
failures, and the runner could not execute inherited selectors for ospec
projects. Tutanota core P2P was empty and therefore did not expose the bug.

## General fix

Pass the constructed environment explicitly into `runOspecHarness`. No task
selector or candidate behavior was hardcoded.

## Tests

- Execution-adapter regression suite including the ospec source contract
  passes after the change.
- Re-run candidate precheck after candidate file ownership and ospec fixes.
