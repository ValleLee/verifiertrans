# Jest verifier-namespace root contract

## Evidence

Element-web rev5 semantic evidence passed and both Hard F2P repeats were runnable but failed with:

```text
yarn test --runInBand --runTestsByPath /app/verifier/verifier.test.tsx
No tests found in /app.
```

Both P2P repeats passed. The manifest explicitly declared `verifier/verifier.test.tsx`; the failure was Jest project `roots` excluding the framework-owned verifier namespace, not shell path concatenation or missing dependencies.

## Root cause

The Node adapter honored the explicit manifest target but did not express the execution-environment requirement for a Jest artifact outside the repository's normal `test/` root. Earlier rev4 also exposed the inverse bypass: the adapter ignored a manifest target under `test/` and executed `/app/verifier/...`.

## Minimal generic fix

`node.functional_command` now keeps the manifest target authoritative and adds `--roots /app --testMatch '**/*.[jt]s?(x)'` only when the declared target is under the generic `verifier/` namespace. Repository-native Jest transforms/configuration remain active; no instance, repository, filename, or test-title special case was added. The existing target-mount logic still mounts the declared source at `/app/{target}`.

## Verification

- deterministic execution adapter tests: 16 passed
- roots-only replay probe still reproduced Jest `No tests found`; the contract was extended with `--testMatch` before the next replay
- full regression suite to rerun after the active E2E
- rev5 evidence remains immutable; the active controller is allowed to finish rev6 and replay with the shared adapter change
