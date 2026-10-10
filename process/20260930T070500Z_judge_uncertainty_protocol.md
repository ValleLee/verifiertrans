# Judge uncertainty protocol (2026-09-30)

## Observation

Positive and negative QA records could contain a top-level `UNCERTAIN` verdict. It
was produced when a model returned an ambiguous value, when the provider did
not return parseable JSON, or when candidate replay and metadata were not enough
to certify the candidate. This made an automatic gate look stalled even though
`UNCERTAIN` was never an acceptance result.

## Generic rule

The LLM Judge has a closed decision set:

- semantic review: `PASS` or `FAIL`;
- positive QA: `VALID` or `INVALID`;
- negative QA: `RELEVANT_NON_EQUIVALENT`, `EQUIVALENT`, or `OFF_TARGET`.

`UNCERTAIN` is not a business verdict. The QA runner retries a protocol failure
up to `experiment.qa_protocol_retries`. If it still cannot obtain a closed
verdict, deterministic evidence is evaluated. A candidate that cannot be
certified is recorded as `INVALID` (positive) or `OFF_TARGET` (negative), with
`judge_verdict: UNCERTAIN` and the protocol details retained for audit. The
summary therefore fails the QA gate and the controller can repair or generate a
new candidate; it never accepts an unresolved candidate.

Semantic review already follows the same rule: malformed or unresolved Judge
output becomes a semantic `FAIL` and enters the revision loop.

## Evidence and limits

A closed verdict does not make an infrastructure failure valid. Replay status,
patch application, expected original/functional outcomes, and candidate
metadata remain deterministic prerequisites. The `judge_verdict` diagnostic is
kept so reviewers can distinguish model protocol trouble from a semantic
rejection without using uncertainty as a hidden pass.

This applies uniformly to all tasks and does not depend on repository names,
instance IDs, test names, or artifact paths.
