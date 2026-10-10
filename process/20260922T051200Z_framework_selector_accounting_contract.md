# Framework issue: canonical selector accounting

- UTC timestamp: 2026-09-22T05:12:00Z
- Instance observed: `instance_NodeBB__NodeBB-04998908ba6721d64eba79ae3b65a351dcfbc5b5-vnan`

## Phenomenon

Prepare produced valid canonical F2P/P2P ids in `restricted/resolved_test_selectors.json`, but the first Converter revision copied raw dataset ids containing the `file | suite` prefix into `manifest.json` and `conversion_trace.json`. Deterministic verifier sanity consequently reported `unaccounted_f2p`, `unexpected_f2p_coverage`, and analogous P2P errors before semantic judging.

## Root cause

The Converter prompt described coverage as “exact source node ids” without explicitly distinguishing the raw dataset `source` list from the executable canonical `resolved` list. The validator correctly compares artifact accounting against the canonical resolved selectors, but the producer contract was underspecified.

## Impact

Revision 1 could not enter Semantic Judge or Core replay. No verifier semantic or NodeBB runtime conclusion was made from this failure.

## General fix

Updated `prompts/converter.md` so all manifest coverage and trace `source_test_id` values must be copied exactly from the corresponding `resolved` selector lists. Raw source provenance may remain in human-readable notes, but cannot be used as the contract id. The existing canonical validator remains authoritative.

## Test result

The current attempt is being resumed through the single Converter REPAIR path. The repaired revision must first pass deterministic verifier sanity, then proceed through Semantic Judge, Hard Validator, replay, and QA gates. No task-specific verifier code was edited.
