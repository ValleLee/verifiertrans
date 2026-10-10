# Framework issue: Jest/TSX metadata selected an unavailable Node loader

## UTC timestamp

2026-09-22T17:06:54Z

## Phenomenon

JavaScript verifier revision 2 passed Semantic Judge and was runnable in Docker, but all P2P groups failed with `ERR_MODULE_NOT_FOUND: Cannot find package 'tsx'`. The discovered execution spec had `runner_family=jest` and `typescript_loader=tsx`.

## Root cause

Execution discovery inferred `tsx` from TypeScript/TSX text in repository metadata. The Node selector runner then unconditionally injected `--import tsx`, even though Jest already owns TypeScript/TSX transformation through its repository configuration and the image did not install the standalone `tsx` package. This mixed runner-level and loader-level responsibilities.

The same revision's F2P `No tests found` result came from the model-generated run.sh/copy contract and remains a verifier artifact issue; it is not folded into this generic loader fix.

## Impact

This was an execution-adapter/framework failure affecting Node repositories with Jest or Vitest. It was incorrectly reported as `VERIFIER_SEMANTIC` because the replay classifier did not recognize missing Node packages; the failure evidence is retained so the next pipeline run can verify the corrected adapter.

## Generic fix

Node selector and package commands now inject `ts-node`/`tsx` only for Mocha. Jest and Vitest receive `--loader none` and use their native configuration. The framework test suite now covers the distinction.

## Test result

- Full test suite after the adapter change: `89 passed`.
- Current JS rev3 continues under the pre-fix attempt metadata; a later fresh Prepare will validate this adapter change end-to-end if rev3 cannot complete with the existing artifact.
