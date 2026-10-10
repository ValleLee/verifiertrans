# Framework model endpoint diagnosis

- UTC: 2026-09-22T08:20:00Z
- Scope: generic external-model infrastructure

## Phenomenon

NodeBB rev4 Semantic Judge requests reach the configured OpenAI-compatible
endpoint but do not return within the 300-second read timeout. The attempt is
therefore recorded as `semantic_rev_4 / INFRASTRUCTURE`.

## Evidence and root cause boundary

- TCP connection to `10.101.56.66:4081`: PASS.
- Unauthenticated HTTP GET to `/chat/completions`: immediate HTTP 405.
- Authenticated model POSTs from the pipeline: repeated read timeouts.

This narrows the failure to model request processing/queueing or endpoint-side
inference latency. It is not a Docker, mount, verifier artifact, or local
network-connectivity failure. Server-side logs are outside this workspace, so
the exact provider-side cause cannot be established here.

## Impact

Rev4 has sanity PASS but cannot receive the required Semantic Judge verdict;
Hard Validator and QA must not be treated as passed or skipped.

## General handling

Keep the immutable rev4 snapshot and retry the same revision when the endpoint
is responsive. Do not start a new Converter revision or classify the timeout as
verifier semantic failure.

## Test result

- Rev4 artifact/sanity: PASS.
- Endpoint TCP/HTTP reachability: PASS.
- Semantic Judge inference: timeout, unresolved.
