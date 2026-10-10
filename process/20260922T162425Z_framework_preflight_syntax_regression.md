# Framework regression: preflight cleanup edit left an invalid try block

## UTC timestamp

2026-09-22T16:24:25Z

## Phenomenon

JavaScript fresh Prepare attempt_004 stopped immediately with a Python `SyntaxError` in `prepare_instance.py`, before Docker execution.

## Root cause and impact

While removing an obsolete temporary staging directory after the preflight mount fix, the surrounding nested `try` block was partially removed. This was a framework implementation regression introduced during the generic fix; it was not task data or infrastructure behavior.

## Fix and test result

The timeout handling was simplified to one valid `try/except subprocess.TimeoutExpired` block. The full test suite passes: `88 passed`. The failed attempt is retained as evidence and a new fresh Prepare attempt will be used.
