# Judge timeout precedence

## Observation

Stage 2 QA runners produced candidate patches and replay results but then remained active for several minutes without a judge.json. The shared environment loader defaults REQUEST_TIMEOUT_SECONDS to the long agent timeout (600 seconds), while configs/experiment.yaml defines a shorter judge_request_timeout_seconds (90 seconds).

## Root cause

agents/judge.py preferred the generic request_timeout_seconds from the environment profile over the dedicated Judge timeout. A stalled or malformed Judge request could therefore delay automatic QA far beyond the configured Judge budget.

## Generic correction

Judge clients now prefer, in order:

1. an explicitly supplied judge_request_timeout_seconds;
2. model.judge_request_timeout_seconds from the experiment config;
3. the generic profile timeout;
4. the model generic timeout fallback.

Agent tool/model requests retain their own longer timeout. This applies to semantic, positive, and negative Judge calls without referencing any task, repository, or instance.

## Verification

The package compiles with python3 -m compileall -q src. Existing in-flight requests may still use the old process configuration; subsequent Judge calls use the bounded timeout and protocol fallback.
