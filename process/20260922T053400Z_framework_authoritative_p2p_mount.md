# Framework issue: authoritative JS P2P replay mount

- UTC timestamp: 2026-09-22T05:34:00Z
- Instance observed: `instance_NodeBB__NodeBB-04998908ba6721d64eba79ae3b65a351dcfbc5b5-vnan`

## Phenomenon

Revision 1 passed sanity and Semantic Judge and correctly separated Base/Gold F2P, but both Base and Gold P2P replay returned verifier rc=2. Logs showed `python3: can't open file '/app/framework/p2p_runner.py'` while setup and patch steps passed.

## Root cause

The generic authoritative replay mounted the framework runner at `/framework` and `/workspace/framework`, while Converter-generated repository-relative `run.sh` executes from `/app` and resolves `framework/p2p_runner.py` under `/app/framework`. Candidate replay already materialized that path, but Base/Gold replay did not.

## Impact

P2P failures were incorrectly attributable to the verifier command even though the verifier was runnable and the missing file was framework-owned. Gold P2P could not pass, so Core correctly routed to Converter REPAIR.

## General fix

`src/verifier_trans/deterministic/replay/verifier.py` now also mounts the framework-owned runner at `/app/framework/p2p_runner.py`, matching the candidate contract and preserving the repository-relative runner interface.

## Test result

The current revision 2 REPAIR is running. Its next Hard Validator replay will verify the mount fix across both Base and Gold without changing the task verifier or selector set.
