# Framework Configuration Repair: Semantic Judge Timeout

- Time: 2026-09-24
- Evidence: element-web rev4 artifact sanity PASS; two semantic-judge attempts each hit `ReadTimeout` at the shared 300-second request timeout. No execution, artifact, or verifier result was produced by those attempts.
- Change: increase the shared model request timeout in `configs/experiment.yaml` from 300s to 600s. This gives the configured DeepSeek judge more response time while preserving the same retry and acceptance gates.
- Scope: shared model transport configuration; no instance/repository/language/test special case.
- Follow-up: resume the immutable rev4 artifact and observe whether semantic validation completes.
