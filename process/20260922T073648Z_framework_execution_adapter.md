# Framework execution adapter contract

- UTC: 2026-09-22T07:36:48Z
- Scope: generic VerifierTrans framework

## Phenomenon

The NodeBB Converter artifact mixed functional assertions with execution
plumbing. It emitted a task-specific `run_p2p.js`, while replay also depended on
the image's Node/Mocha layout, `/app` versus `/workspace` paths, and Redis
startup. A failure in any of those layers looked like a verifier failure.

## Root cause

The Converter prompt and the Hard Validator did not enforce a single ownership
boundary for runner selection, cwd, mounts, and service bootstrap. The model
could satisfy the old `run.sh` contract by implementing a second P2P runner.

## Impact

The verifier was coupled to private execution details and could report false
semantic failures. In this instance rev2 reached Core PASS only after a
model-generated Node runner was used; rev3 still contained that runtime file.

## General fix

Hard Validator remains the existing role, but now calls the deterministic
`deterministic/execution` adapter. It selects native Python/Node/Go commands,
mounts framework-owned runners, and starts optional Redis. Converter artifacts
are sanity-rejected when `run.sh` or verifier files contain task-specific P2P,
selector, Docker, or service runtime plumbing. Package generation uses the same
adapter contract. The Converter prompt now defines only functional semantics,
mapping, and accounting.

## Test result

- `python3 -m compileall -q src tests`: PASS.
- `timeout 60 .venv/bin/pytest -q tests/unit/test_execution_adapters.py tests/unit/test_verifier_replay_entrypoint.py tests/unit/test_candidate_replay_mounts.py tests/unit/test_candidate_replay_contract.py`: 7 passed.
- NodeBB rev3 must be revalidated because the previously running controller
  loaded the old contract before this fix.
