# Mini-SWE repeated-format recovery

## Observation

The Element repair agent exited with RepeatedFormatError before producing any revision artifact. This occurred while the Docker workspace was never started, so the failure was agent protocol transport rather than verifier or test execution.

## Generic correction

The converter runner now retries one fresh mini-SWE session when the exit status is exactly RepeatedFormatError. The retry adds a short protocol reminder requiring one bash tool call per response and the completion sentinel. Other agent failures remain bounded failures and do not receive semantic fallback.

## Scope and safety

The retry is task-agnostic, does not inspect instance names or test symbols, and does not edit generated artifacts. A successful retry still must pass the artifact, semantic, Docker replay, stability, and QA gates.

## Verification

The source compiles with python3 -m compileall -q src. The Element and Tutanota attempts that already timed out remain recorded; future retries use the new recovery path.

## Retry outcome

A subsequent retry of Element did not create a new Docker workspace and exited
with the same mini-SWE protocol failure; Tutanota likewise produced no revision
artifact before its timeout. Both remain rejected and are excluded from final.

## Follow-up correction

The retry alone was insufficient because mini-swe-agent's default
`max_consecutive_format_errors=3` terminated a session before the protocol
reminder could take effect. Converter, QA, and shared mini-SWE sessions now use
an explicit configurable tolerance of 6 consecutive format errors, while the
outer controller still requires a real submitted artifact and all deterministic
and QA gates.
