# Framework Positive QA legacy-test distinctness contract

- UTC: 2026-09-22T07:36:49Z
- Scope: generic VerifierTrans QA framework

## Phenomenon

Positive evidence recorded P2P success and an LLM `VALID` verdict, but did not
prove that the alternative implementation differed from the historical F2P
test-specific implementation. In the current NodeBB attempt, the candidate's
converted F2P replay also failed, so the old evidence was not sufficient for
acceptance.

## Root cause

Positive QA appended evidence before running deterministic converted F2P, and
there was no execution group for the historical `fail_to_pass` selectors.

## Impact

An implementation could be labeled a valid alternative without demonstrating
the intended verifier tolerance. Older evidence could also be reused after the
QA contract changed.

## General fix

Positive precheck and post-Judge verification now run `p2p`, converted `f2p`,
and `legacy_f2p`. A positive is accepted only when all are runnable, current
F2P and P2P pass, and historical F2P is runnable but fails. Evidence stores
`legacy_f2p_expected_fail: true`; replay rejects older evidence without that
field. Resume also invalidates an otherwise accepted final lacking this proof.
The Positive Generator and Judge prompts describe the same contract.

## Test result

- Positive execution contract is covered by orchestrator evidence fields and
  replay logic.
- Existing positive evidence for NodeBB is intentionally invalidated and will
  be regenerated on the next resume.
- The deterministic adapter/unit test suite passes 7 tests.
