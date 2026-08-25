# Debug Adapter Gateway Contract

## Purpose

The gateway normalizes DAP, CDP and native adapters without pretending that all adapters have identical capabilities.

## Handshake

An adapter must return: adapter name/version/digest, runtime kind/version, protocol version, capability list, source-map strategy, supported launch/attach modes, expression policy support, replay level and limits.

## Control semantics

- Every command has `command_id` and monotonic `sequence`.
- Read-only queries may be retried; execution commands are never silently replayed.
- Events carry the adapter sequence and gateway sequence.
- Breakpoints are validated against a fixed revision and source mapping.
- Variable references are session-local, opaque and expire with the pause generation.

## Safety

- Evaluate is read-only by default.
- Adapter output is untrusted and size-limited.
- The adapter has no direct access to tenant credentials or control-plane storage.
- Binary/image digest and capability matrix are recorded in the session manifest.

## Termination

The gateway waits for bounded graceful shutdown, then kills the adapter and target through the sandbox orchestrator. Cleanup attestation is required before resources return to the pool.
