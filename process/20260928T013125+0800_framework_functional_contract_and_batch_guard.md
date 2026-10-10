# Framework process record: functional-contract audit and batch guard

- **Observed at:** 2026-09-28 01:31:25 +0800
- **Scope:** instruction generation, verifier validation, package contract, and preparation CLI
- **Goal:** keep converted SWE-bench Pro tests focused on observable behavior and make repeated/batch conversion fail closed on invalid inputs.

## Findings

1. Generated instructions and semantic review guidance did not consistently distinguish legitimate API-visibility requirements from implementation-bound test coupling. This was especially visible for Go tasks whose historical tests mention unexported client types and constructors.
2. Validation had no deterministic solver-facing instruction audit. A conversion could pass behavioral checks while retaining historical selectors, absolute paths, or exact layout/mock/AST requirements in `instruction.md`.
3. The generated grader lacked a stable patch-path inspection entrypoint for external package smoke checks.
4. Empty P2P selector sets were represented by an invented placeholder node, obscuring that the source task had no P2P evidence.
5. A malformed shell invocation with an empty `--data` expansion entered preparation instead of failing at the CLI boundary.

## Framework changes

- `prompts/converter.md` and `prompts/judges/semantic.md` now require public-contract or observable-behavior wording and prohibit concrete private names, package paths, file layouts, AST/name heuristics, and mock call shapes in solver-facing instructions. API visibility is retained only when supported by F2P evidence.
- `deterministic/validation/instruction_policy.py` adds a deterministic hard-fail audit for path, selector, layout, mock, and AST coupling; visibility terms are advisory. `validate_verifier.py` records the result in verifier evidence and fails the revision on hard errors.
- `packaging/package_task.py` adds `grader.py patch-paths PATCH` and records `p2p_present`/`p2p_policy`; empty P2P is explicitly `source_empty_noop` with no synthetic node.
- `pipeline/orchestrator.py` rejects missing or empty preparation dataset paths before starting the worker.

## Verification

- VerifierTrans suite: `144 passed`.
- Instruction-policy tests: 3 passed; artifact regression tests: 1 passed.
- Empty-path smoke check: rejected with `prepare data file does not exist: .` and did not create an attempt.
- A fresh Navidrome `attempt_006` was prepared successfully; source preflight and repository materialization both passed (`123799` files, `836M`). Full model-driven conversion was not run in this record because the execution approval did not identify a trusted external model destination.

## Remaining risk

The deterministic audit is intentionally conservative and should be monitored for false positives when instructions describe implementation details only to exclude them. The external-model execution policy remains an operational prerequisite for end-to-end reruns; once an approved trusted destination is provided, Navidrome and qutebrowser must be rerun and their new instruction/verifier/package artifacts inspected.

## Follow-up: model endpoint failure classification

The fresh Navidrome attempt reached Converter revision 1, but the configured endpoint returned HTTP 402 `Insufficient Balance`. The controller first recorded `MANUAL_REVIEW` and advanced to revision 2, which would have wasted revision budget without changing the cause. This is an infrastructure/model-endpoint failure, not a verifier repair opportunity.

`pipeline/orchestrator.py` now classifies HTTP 400/401/402/403/404 account, authentication, permission, and balance failures as non-retryable `MODEL_ENDPOINT` infrastructure failures and stops the attempt. Transient 429/5xx errors and ordinary tool-step failures retain their existing retry/partial-repair paths. Regression coverage is in `tests/unit/test_orchestrator_state.py`; the relevant tests pass (`19 passed`).

The attempt was resumed with the fixed controller and now terminates as `INFRASTRUCTURE` / `MODEL_ENDPOINT` (`retryable: false`) in `control/state.json` and `run/final.json`. No Semantic Judge, Hard Validator, QA, package, or final_task evidence was claimed.

## Follow-up: package grader contract

The generated grader previously treated one F2P and one P2P exit code as the entire grading contract. It now supports DeepSWE-style config whitelists, CTRF/JUnit report parsing, worst-status merging, missing-node failure, vacuous empty-P2P scoring, binary reward, partial reward, `apply_failed`, and ordered `patch-paths`; the legacy `grade F2P_RC P2P_RC` entrypoint remains for the generated `test.sh`. Package grader regression tests pass (`2 passed`), and the full VerifierTrans suite passes (`147 passed`).

## Follow-up: explicit terminal states

`run/report.json` previously labeled every unsuccessful attempt `MANUAL_REVIEW`, even when `run/final.json` and `state.json` already identified infrastructure or package failures. The controller now maps outcomes to `FINAL_VALIDATED`, `INFRASTRUCTURE`, `PACKAGE`, or `FAILED`; automatic conversion has no implicit human-review queue. The terminal Navidrome report was aligned to `INFRASTRUCTURE / MODEL_ENDPOINT`.

A fresh qutebrowser `attempt_004` was prepared after the controller/package changes. Source and environment preflight passed, with 4 F2P selectors and 52 P2P selectors resolved; repository materialization passed (`936` files, `20M`). It is intentionally left at Prepare until the sole configured model endpoint has available balance; no old verifier evidence is reused.

Final regression after all changes: `149 passed` in the VerifierTrans test suite. This includes the generated grader contract tests, endpoint classification, explicit terminal-state mapping, and instruction policy tests.

## Follow-up: QA endpoint failures and qutebrowser fresh evidence

Fresh qutebrowser `attempt_004` reached Converter submission, Semantic PASS, and Hard Gate PASS: Base F2P failed, Gold F2P passed, Base/Gold P2P passed, and stability passed for 4 F2P / 52 P2P selectors. Positive QA then received HTTP 402 twice and would have continued to a third solver attempt. The controller now stops Positive or Negative QA immediately on the same non-retryable `MODEL_ENDPOINT` classification. The run was stopped before further spend; its core evidence remains immutable.

After propagating the classifier through QA, the full VerifierTrans regression suite passes (`150 passed`).

qutebrowser `attempt_004` was resumed with the fixed controller. It re-used only its own immutable semantic/core evidence, then stopped at the first Positive QA endpoint error with terminal `INFRASTRUCTURE / MODEL_ENDPOINT`; the report records Core Gate PASS and no positive/negative QA claim.

The endpoint briefly accepted a minimal health request, so a new Navidrome `attempt_007` was created and Prepare passed. Its Converter explored the repository and emitted a partial session, but the same endpoint returned HTTP 402 before submission; the controller terminated it as `INFRASTRUCTURE / MODEL_ENDPOINT` without claiming verifier evidence. This confirms the remaining blocker is service quota, not the framework's retry classification.
