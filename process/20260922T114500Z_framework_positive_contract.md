# Step 3: relaxed Positive QA contract

- UTC: 2026-09-22T11:45:00Z
- Stage: C / Positive QA
- Scope: controller/evidence contract only; no fresh task or model/API call.

Positive acceptance now requires only current converted F2P PASS, retained P2P PASS, and a
`VALID` Solution Judge result. Historical F2P is still replayed and stored as
`historical_f2p_runnable` / `historical_f2p_pass`; PASS, FAIL, or historical infrastructure
failure is audit evidence and cannot reject a candidate that satisfies the current contract.

The controller replays P2P and current F2P after the Judge decision. Evidence uses
`contract_version: 2`; old evidence is retained for audit and revalidated under the current
contract instead of being silently trusted or discarded. The Positive generator and Judge
prompts use the same relaxed rule. Historical F2P remains outside final package reward.

## Verification

- `tests/unit/test_positive_qa_contract.py`: 4 passed.
- Combined focused execution/package/QA tests: 11 passed.
- Source compilation passed.

No new Agent or Pipeline state was introduced; the version is evidence schema metadata only.
