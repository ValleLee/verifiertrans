# Framework issue: Node P2P runner started one process per selector

## UTC timestamp

2026-09-22T17:31:41Z

## Phenomenon

Element Web core revision 3 reached deterministic replay, but Node P2P replay timed out while executing 39 inherited selectors. The result was correctly classified as `INFRASTRUCTURE` and entered the one permitted `INFRA_RETRY`.

## Root cause

The framework-owned Node runner spawned Jest/Vitest once for every test case. Each process repeatedly paid repository startup and transformation cost, making a large P2P list exceed the replay timeout even though the individual tests were executable.

## Generic fix

The Node execution adapter now batches all selectors belonging to one file into one native-runner invocation and combines their escaped titles into a single precise test-name regex. Jest/Vitest retain their repository-native execution; no task-specific selector or timeout exception was added.

## Test result

- Full framework test suite after batching and loader selection fixes: `90 passed`.
- The active JS attempt's infrastructure retry will use the updated framework-owned runner mount. If the retry succeeds, its artifact remains reusable; otherwise the next action is determined from the retry evidence.
