# Framework Repair: Node Functional Runner Must Consume ExecutionSpec

- Time: 2026-09-24
- Trigger instance: element-web fresh attempt

## Evidence

- Prepare froze `ExecutionSpec` as `runner_family=jest`, `package_manager=yarn`, TypeScript/TSX project.
- P2P replay used the framework Jest runner and passed 39/39.
- F2P replay failed identically on Base and Gold before loading any assertion: `TypeError [ERR_UNKNOWN_FILE_EXTENSION]: Unknown file extension ".tsx" for /app/verifier/verifier.test.tsx`.
- `src/verifier_trans/deterministic/execution/node.py::functional_command` unconditionally emitted `node /app/verifier/<artifact>`, bypassing the frozen Jest contract.

## Minimal generic repair

- Jest functional artifacts now run through the frozen package manager test command with `--runInBand --runTestsByPath /app/verifier/<artifact>`.
- Vitest uses its native `run` command. Existing executable-artifact compatibility remains for Mocha/ospec paths.
- No task/repository/test-title/filename special case was added.

## Verification

- Added `test_jest_functional_artifact_uses_native_runner` to `tests/unit/test_execution_adapters.py`.
- Adapter and judge parser tests: 18 passed.
- Element-web rev2 evidence showed the bug is an ExecutionSpec bypass; Converter rev3 is now being re-run after the framework fix.
