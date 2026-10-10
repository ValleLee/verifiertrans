# Infrastructure issue: Luna High model access

- Time (UTC): 2026-09-23T21:08:15+00:00
- Scope: Round2 model selection
- Trigger: qutebrowser fresh attempt_002

## Evidence

The configured API key accepted `deepseek-v4-pro-Code-PT-SWE-Pro-o-66` but returned HTTP 403 `key_model_access_denied` for `deepseek-v4-flash-Code-PT-SWE-Pro-a-66`. The response explicitly listed the only model allowed by the key. Prepare/preflight had already passed; no Converter artifact or verifier evidence was produced in attempt_002.

## Classification

`INFRASTRUCTURE` / external model authorization. This is not a repository, selector, verifier, or shared execution-contract defect.

## Action

Restored `DEFAULT_MODEL` to the key-authorized pro model. Luna High remains unavailable for this `.env` key; no workaround or key output was attempted. Subsequent Round2 runs use the authorized model and retain this attempt as infrastructure evidence only.
