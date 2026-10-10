# Framework issue: Positive QA did not require legacy-test separation

- UTC timestamp: 2026-09-23T00:37:39Z
- Scope: TypeScript/Tutanota attempt_014 Positive QA

## Symptom

The candidate passed current functional F2P and P2P, and the Positive Judge
returned `VALID`, but the QA contract still accepted it when historical F2P
also passed. This contradicted the experiment requirement that an alternative
implementation demonstrate current-verifier acceptance while failing the old
test contract.

## Root cause

`positive_execution_contract` intentionally treated historical F2P as audit
only. The precheck also gated only current F2P/P2P, so a candidate that did
not expose the intended verifier generalization could become a Positive.

## Impact

Positive QA could not serve as hard evidence that the converted verifier was
more implementation-tolerant than the historical tests.

## General fix

Positive acceptance now requires all of:

- current functional F2P PASS;
- retained P2P PASS;
- historical F2P runnable and FAIL.

The precheck and final post-Judge contract both enforce this separation. A
legacy infrastructure failure is not treated as proof of semantic separation.

## Tests

- QA contract/execution/orchestrator regressions: `21 passed`.
- Existing candidate evidence must be revalidated under the new contract; the
  old accepted evidence is no longer sufficient.
