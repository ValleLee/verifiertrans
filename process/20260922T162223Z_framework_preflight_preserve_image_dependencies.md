# Framework issue: Node preflight masked image-provided dependencies

## UTC timestamp

2026-09-22T16:22:23Z

## Phenomenon

JavaScript Prepare attempt_003 resolved all logical-root selectors and test files, and Docker, Node, and Yarn were available. Jest collection nevertheless returned exit code 1 because `node_modules/.bin/jest` was absent in the preflight container.

## Root cause

The preflight command bind-mounted the host-materialized repository directly at `/app`. Materialization intentionally excludes bulky runtime directories such as `node_modules`, because the task image is the source of those dependencies. The bind mount consequently hid the image's prepared `/app/node_modules` and made a valid Node runtime appear unavailable.

## Impact

This was an execution-layer/framework failure before Converter execution. It could affect JavaScript/TypeScript repositories even when their Docker images contain the correct dependencies. It was unrelated to verifier semantics, selectors, or the Element Web task itself.

## Generic fix

Preflight now mounts the prepared source tree at `/source` and copies it over the image's `/app` checkout. It no longer mounts the incomplete host tree over `/app`, so image-provided dependencies remain visible while the checked-out source is validated. The existing replay/candidate execution adapters already use the image's `/app` runtime and were not given a task-specific exception.

## Test result

- Full framework test suite after the change: `88 passed`.
- Next validation: fresh JavaScript Prepare attempt; attempts 001–003 remain immutable evidence.
