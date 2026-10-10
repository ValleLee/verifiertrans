# Framework fix: execution-adapter Docker mounts were appended after the image

- UTC: 2026-09-22T15:18:24Z
- Discovered during: Step 5 qutebrowser fresh attempt, verifier revision 3
- Scope: generic replay execution layer; no task-specific code

## Phenomenon

The qutebrowser verifier passed semantic review and was runnable for F2P, but both Base and Gold P2P replay exited with verifier return code 2. The replay log reported:

```text
python3: can't open file '/framework/p2p_runner.py': [Errno 2] No such file or directory
```

The container itself started successfully, so this initially looked like a P2P artifact problem.

## Root cause

`deterministic/replay/verifier.py` appended `ExecutionPlan.mounts` after the Docker image reference and `-lc` script. Docker interprets options after the image as container command arguments; therefore the framework-owned Python P2P runner mount was never installed at `/framework/p2p_runner.py`.

## Impact

All language adapters using replay-time runner mounts could fail P2P before executing any selected test. The failure was generic execution infrastructure, not verifier semantics, selector content, repository cwd, or Docker availability.

## Generic fix

Added `build_replay_command()` and moved every adapter mount before the image reference. The replay command now has the form:

```text
docker run [framework/verifier/service mounts] IMAGE -lc SCRIPT
```

The Converter contract and the single Pipeline were not changed. The Hard Validator remains responsible for runner mounts and native execution.

## Tests

- New regression test verifies adapter mounts precede the image and `-lc` script.
- Execution/replay contract tests: 12 passed.
- Full framework pytest suite: 84 passed.
- Replayed the existing qutebrowser rev_3 artifact after the fix without another model call: `base_p2p_pass=true`, `gold_p2p_pass=true`, `stable=true`.
- The same replay still reports `base_f2p_pass=true`; that remaining failure is verifier semantic evidence and must be handled by Converter REPAIR.
