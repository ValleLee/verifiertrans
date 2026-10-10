# Framework issue: stale Positive evidence still counted during resume

- UTC timestamp: 2026-09-23T00:39:48Z
- Scope: TypeScript/Tutanota attempt_014 after Positive contract v3

## Symptom

The old evidence file recorded a Positive under contract v2, before legacy F2P
separation was a hard condition. On resume, the controller logged a
revalidation but retained the stale item in the in-memory positive list, so
the QA loop could skip deterministic revalidation and proceed to Negative QA.

## Root cause

Stale evidence was preserved for audit but was also counted toward the current
positive target. The contract-version check was therefore informational rather
than gating.

## General fix

Only positives with the current `POSITIVE_CONTRACT_VERSION` enter the active
evidence list. Older entries remain on disk for audit and their payloads are
revalidated by name; they cannot satisfy the current target until the new
current/legacy/P2P contract is proven.

## Tests

- Positive QA/orchestrator targeted tests cover contract v3 and stale-entry
  filtering.
- Resume the existing attempt; the previous legacy-PASS candidate must be
  rejected or replaced before Negative QA starts.
