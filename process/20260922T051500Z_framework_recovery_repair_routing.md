# Framework issue: recovery failure must route to REPAIR

- UTC timestamp: 2026-09-22T05:15:00Z
- Instance observed: `instance_NodeBB__NodeBB-04998908ba6721d64eba79ae3b65a351dcfbc5b5-vnan`

## Phenomenon

After revision 1 failed deterministic artifact sanity, `resume` recorded `resume_recovery` but started another Converter revision with `repair=false`. This would silently repeat BUILD even though the controller had concrete verifier-sanity evidence requiring repair.

## Root cause

The recovery branch initialized a failure report but did not populate the controller's `repair_packet`; the normal revision loop therefore treated the existing submitted artifact as a fresh BUILD when no immutable revision snapshot existed.

## Impact

The first resumed process could consume model steps without using the required single-Converter REPAIR mode. It was stopped before producing a replacement artifact. No unrelated run was touched.

## General fix

`src/verifier_trans/pipeline/orchestrator.py` now converts recovery sanity evidence into the ordinary `repair_packet` before entering the revision loop. The next converter invocation is explicitly REPAIR and preserves the accumulated diagnosis.

## Test result

The corrected resume path is being exercised on the same 049989 attempt. The repaired artifact must pass sanity before any later gate is considered. The change is generic and does not mention NodeBB behavior.
