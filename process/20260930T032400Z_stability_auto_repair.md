# Stability failure automatic repair

## Observation

The Element task passed artifact, semantic, and Base/Gold replay gates, but stability replay found that the candidate retained only 5 P2P selectors while the original had 39. The controller stopped with rejected_stability and repair_count 0.

## Root cause

The orchestrator routed a stability failure directly to finish(), unlike artifact, semantic, hard replay, and QA failures. That left a known generic verifier defect without the automatic mini-SWE repair loop required by the pipeline.

## Generic correction

Stability failures now call the existing bounded _retry_or_finish() path with gate=stability. A new revision receives the recorded replay evidence and is revalidated from the artifact gate. The no-qa option still exits successfully only after stability passes.

## Verification

The source compiles with python3 -m compileall -q src. The Element task will be resumed through the updated controller; its retained P2P mismatch remains evidence for the repair agent rather than being manually overridden.
