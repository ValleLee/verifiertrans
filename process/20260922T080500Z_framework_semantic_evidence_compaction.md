# Framework Semantic Judge evidence compaction

- UTC: 2026-09-22T08:05:00Z
- Scope: generic model-backed validation infrastructure

## Phenomenon

Semantic Judge requests for NodeBB repeatedly reached the 300-second HTTP
timeout. The rev4 Converter trajectory itself had a normal 41-call, 84-message
repair session and submitted successfully; the slow request occurred in the
separate post-conversion Semantic Judge.

## Root cause

The semantic evidence used the complete verifier tree, including a 37 KB
manifest with the full P2P list and a 34 KB `p2p_nodes.txt`, even though exact
P2P accounting and execution are deterministic responsibilities. This inflated
the model context without improving F2P semantic review.

## Impact

The API spent two 300-second attempts on an oversized request and left rev4
unjudged. This was an efficiency/infrastructure issue, not a verifier semantic
failure.

## General fix

Semantic Judge now receives F2P trace/log/scope and implementation files, while
`p2p_nodes.txt` is omitted and manifest P2P coverage is represented only by a
count/presence summary. Deterministic sanity and Hard Validator retain the
complete exact P2P coverage checks.

## Test result

- rev4 sanity remains PASS.
- The next resume retries Semantic Judge with compact evidence and keeps the
  same immutable rev4 artifact.
