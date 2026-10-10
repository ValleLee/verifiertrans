# Framework convergence plan baseline audit

- UTC: 2026-09-22T09:20:00Z
- Scope: Step 0 of `docs/plan_optimize.md`; no external model, Docker task, or fresh validation task was started.
- Paused task: NodeBB conversion remains paused; no attempt was resumed or mutated.

## Observed baseline

The repository baseline is `70 passed in 10.54s` under `.venv/bin/python -m pytest -q`.
The existing execution layer already provides language normalization, separate Python/Node/Go
adapters, replay/package command construction, framework runner mounts, and bounded Redis
bootstrap. It does not yet discover repository-native runner metadata; the Node selector helper
is still Mocha-oriented; and non-Python preflight is not equivalent to Python preflight.

`package_task.py` still concatenates the complete `restricted/original_test.patch` with the
converted verifier files. The final `test.sh` does not invoke `legacy_f2p`, but the physical
test patch is therefore not yet accounted as P2P-only/shared/F2P-only content.

`orchestrator.py` still requires `legacy_f2p_expected_fail` for Positive QA, invalidates
evidence without that field, and reruns historical F2P as a hard acceptance condition. This
differs from the revised contract: current converted F2P + P2P + Solution Judge establish
validity; historical F2P PASS/FAIL is audit evidence only.

`paths.py` remains attempt-centric: source material is under
`intermediate/attempts/attempt_NNN/source`. The desired instance-root `source/` boundary and
layout manifest are not implemented. Existing `.compat` links and old attempts must remain
readable while this is changed.

## Step 0 result

Baseline is reproducible, no old evidence was rewritten, and the paused NodeBB/API state is
unchanged. The four implementation gaps above are framework-level and are addressed in order
A, B, C, D with focused tests before each next step.
