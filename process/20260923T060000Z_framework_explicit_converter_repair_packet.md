# Framework issue: interrupted QA had no explicit Converter REPAIR handoff

- UTC: 2026-09-23T06:00:00Z
- Scope: generic controller resume/repair contract
- Observed during: TypeScript/Tutanota `attempt_001`, verifier semantic audit

## Phenomenon

The controller can route QA evidence to Converter REPAIR when the evidence is
created inside one uninterrupted controller process. After an intentional
interruption during Positive QA, the immutable revision and QA evidence were
preserved, but the in-memory `repair_packet` was lost. The CLI exposed only
normal `run`/`resume`, so resuming would continue Positive QA against the
known-defective verifier instead of starting the required REPAIR revision.

## Root cause

Evidence-led repair was represented only as an in-memory controller variable;
there was no generic persisted packet contract for an operator or automated
recovery step to hand structured Judge/Hard Validator/QA evidence to the same
Converter implementation.

## Impact

An interrupted experiment could waste more candidate attempts or require an
ad-hoc direct Python call, weakening reproducibility and making it difficult to
prove that the next revision used Converter REPAIR rather than a fresh BUILD.

## General fix

Added `--repair-packet PATH` to the run/resume argument contract. The packet is
validated as a JSON object, logged as `REPAIR_REQUESTED`, and forces a new
revision with `args.resume = False`; the existing `run_converter` then selects
REPAIR mode from the non-empty packet. No instance, repository, commit, or
test-name special case is involved.

## Tests

- Added a controller source regression covering packet loading, event logging,
  and new-revision routing.
- The Tutanota semantic evidence will be handed to this generic path in the
  next run; no unrelated containers, images, or runs are removed.
