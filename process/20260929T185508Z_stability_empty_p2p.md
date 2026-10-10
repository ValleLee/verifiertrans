# Stability handling for tasks without retained P2P selectors

## 现象

OpenLibrary task `...72321288...` had zero original P2P selectors. Its functional F2P replay passed twice and the Gold replay passed twice, but stability returned `fail` because the generic predicate required `len(original_p2p) > 0`.

## Failure classification

Framework-level validation logic. The condition applies to any task whose original Harbor config has an empty `pass_to_pass` list.

## 修复

`validation/stability.py` now treats an empty original P2P set as a valid no-op obligation: the candidate must also contain no P2P selectors and no P2P replay is required. Tasks with retained P2P selectors still require exact selector preservation and repeated Base/Gold P2P passes.

## 验证

The OpenLibrary functional F2P replay had Base FAIL / Gold PASS on both repeats before this correction. The revision is being re-run through stability and downstream QA with the corrected predicate. Python compileall passes.

## Follow-up correction (2026-09-30T03:xxZ)

The first predicate repair still rejected a zero-P2P task because the runner
creates bookkeeping preflight replays with an empty selector set. The generic
rule is now: when the original P2P set is empty, require candidate P2P to stay
empty and require every generated bookkeeping replay to pass. This preserves
the no-selector contract without treating the existence of an empty harness as
an obligation failure.
