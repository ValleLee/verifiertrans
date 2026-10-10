# Step 5 checkpoint: qutebrowser complete

- UTC: 2026-09-22T16:10:12Z
- Instance: `instance_qutebrowser__qutebrowser-f91ace96223cac8161c16dd061907e138fe85111-v059c6fdc75567943479b23ebca7c07b5e9a7f34c`
- Fresh attempt: `intermediate/attempts/attempt_002`
- Final verifier revision: `rev_003`
- ExecutionSpec: Python / pytest / pip; cwd `.`; module_root `.`; no services

## Gate results

- Prepare/Preflight: PASS; Base checkout and Docker toolchain checks passed.
- F2P accounting: 4/4 mapped; P2P accounting: 52/52 retained.
- Semantic Judge: PASS on rev_3.
- Hard Validator: PASS and stable; Base F2P FAIL, Gold F2P PASS, Base/Gold P2P PASS.
- Positive QA: `positive_1_attempt_3` VALID; current F2P and P2P PASS.
- Negative QA: `mutant_1_attempt_1` and `mutant_2_attempt_2` both `RELEVANT_NON_EQUIVALENT`; P2P PASS and current F2P rejected.
- Package smoke: PASS.
- final_task: generated successfully.

## Framework issues found in this task

1. Core replay appended execution-adapter Docker mounts after the image reference. Fixed in `deterministic/replay/verifier.py`; existing rev_3 artifact revalidated with P2P PASS.
2. Candidate replay had the same mount-order defect. Fixed in `deterministic/replay/candidate.py`; the first Positive candidate's infrastructure failure was distinguished from its later semantic retries.
3. A repair packet from an earlier sanity failure was not cleared after a later revision passed sanity, causing a false `QA_DEFECT`. Fixed in `pipeline/orchestrator.py`; resume reused rev_3 and completed Negative QA/package without another Converter call.

Framework regression suite after these fixes: 85 passed.

## Final artifact

`/lg-home/cog8/lwli6/VerifierTrans/runs/instance_qutebrowser__qutebrowser-f91ace96223cac8161c16dd061907e138fe85111-v059c6fdc75567943479b23ebca7c07b5e9a7f34c/final_task`
