# Framework issue: ospec harness was launched from the repository root

- UTC timestamp: 2026-09-23T00:32:51Z
- Scope: TypeScript/Tutanota Positive QA legacy-F2P replay

## Symptom

After fixing the undefined ospec environment, legacy F2P still failed before
tests ran because the harness attempted to import `/app/TestBuilder.js`.
Tutanota's `test/test.js` resolves `TestBuilder.js` relative to its cwd, so
the framework-owned runner must start it from `/app/test`.

## Root cause

The generic ospec adapter invoked `node test/test.js` with cwd equal to the
repository root. This worked neither for the project's native path contract
nor for exact legacy comparison.

## Impact

Legacy F2P failure was a module-not-found infrastructure error and could be
mistaken for evidence that a Positive candidate failed the old test. The
current functional verifier was unaffected.

## General fix

When a repository has `test/test.js`, the ospec adapter now uses `test/` as
the harness cwd and invokes `node test.js`; repositories without that layout
retain the discovered app cwd. No repository or task path is hardcoded.

## Tests

- Execution-adapter source regression updated for env propagation and harness
  cwd.
- Re-run the existing candidate's legacy F2P comparison before accepting QA.
