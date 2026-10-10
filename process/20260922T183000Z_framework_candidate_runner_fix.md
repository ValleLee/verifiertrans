# Framework issue: QA candidate P2P runner was not available in `/app`

## Observation

The first Positive QA candidate was a runnable three-file alternative payload,
but its deterministic precheck failed before any semantic Judge decision:

```text
python3: can't open file '/app/framework/p2p_runner.py': [Errno 2] No such file or directory
```

The candidate replay container mounted the framework runner at
`/workspace/framework/p2p_runner.py`, while the Converter's repository-relative
`run.sh` correctly invoked `framework/p2p_runner.py` after `cd /app`. The
candidate runner therefore had an inconsistent workspace contract. The result
was also incorrectly classified as `VERIFIER_SEMANTIC`.

## Fix

The generic candidate replay script now copies the read-only framework runner
from `/workspace/framework/p2p_runner.py` to `/app/framework/p2p_runner.py`
before running any candidate verifier. Missing runner errors are classified as
`INFRASTRUCTURE`, so they cannot contaminate QA evidence or trigger a semantic
verifier repair.

The same bootstrap now copies the prepared
`resolved_test_selectors.json` into `/app/restricted`, because candidate
`run.sh` executes from `/app` and is intentionally repository-relative. QA also
reuses a previously generated candidate when its only recorded failure is this
kind of deterministic infrastructure precheck, avoiding an unnecessary new
model generation.

This is a role/replay contract fix and is independent of qutebrowser code.
The failed candidate remains recorded as `positive_1_attempt_1`; it is not
adjudicated and is not counted as QA evidence. The same generated payload will
be rechecked after the fix.
