# Positive QA semantic-validation layering

## Phenomenon

Positive QA previously required `current_f2p_pass` before invoking the Solution
Judge. A structurally different candidate that was functionally valid but
rejected by the current verifier therefore disappeared as an ordinary failed
candidate. The controller had no way to distinguish a bad generated positive
from a verifier false negative.

## Root cause and classification

This is a generic QA state-machine/framework defect, not a task-specific
candidate defect. The deterministic current-F2P result was incorrectly used
as the semantic oracle for the candidate that the verifier itself was supposed
to be tested against.

## General repair

Positive QA now records three layers:

1. `candidate_positive`: deterministic precheck confirms runnable P2P, runnable
   converted F2P, P2P PASS, and structural difference from Gold. A runnable
   current-F2P semantic failure remains eligible for adjudication.
2. `validated_positive`: the Solution Judge independently returns `VALID`.
   Historical F2P remains audit evidence only.
3. accepted positive: the validated candidate also passes the current F2P and
   P2P replay.

If a `validated_positive` has a runnable semantic current-F2P failure, the
controller emits `VERIFIER_FALSE_NEGATIVE` and routes structured evidence to the
single Converter REPAIR path. Candidate-invalid and infrastructure failures do
not trigger verifier repair.

The contract version was incremented so old positive evidence is not silently
treated as satisfying the new state machine. The positive Judge prompt now
explicitly says that current-verifier rejection is evidence, not a reason to
reject semantic validity.

## Test result

Targeted regression suite:

```text
24 passed in 27.78s
```

Covered cases include historical-F2P audit-only behavior, runnable current-F2P
semantic failure reaching adjudication, validated-positive false-negative
routing, invalid-candidate soft failure, and infrastructure non-escalation.
