# 2026-09-24 quoted-heredoc literal/path guard repair

## Evidence

During the Tutanota converter repair, the workspace shell validator rejected
commands containing `..` or an absolute-looking token even when those tokens
were source literals inside a quoted heredoc, for example `../api/common` or
`</script>`. This interrupted scratch/prototype writes and inflated converter
repair attempts. The guard was intended to prevent path traversal, not to
reject inert source text.

## Minimal generic repair

`workspace_tools.validate_bash` now masks the bodies of *quoted* heredocs
(`<<'EOF'` / `<<"EOF"`) before applying traversal and absolute-path checks.
The heredoc header and delimiter remain checked, and unquoted heredocs remain
fully checked because shell substitutions may execute. No instance, language,
test-title, or verifier filename is special-cased.

## Deterministic validation

Added isolation tests for a quoted-heredoc source literal and for traversal in
the heredoc header. The targeted suite passes: `18 passed`.

## Boundary

This only removes a false positive for inert quoted-heredoc content. It does
not relax workspace roots, absolute-path checks in command text, or shell
expansion checks in unquoted heredocs.
