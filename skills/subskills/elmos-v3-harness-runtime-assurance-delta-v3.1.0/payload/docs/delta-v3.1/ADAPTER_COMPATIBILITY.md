# Adapter Compatibility

| Profile | Status | Required behavior |
|---|---|---|
| Codex 0.150.1 | stable baseline | Do not advertise main-only result interception or invocation-lifetime extension SPI |
| Codex main @ 2026-08-28 | pre-stable pinned | Exact commit pin and conformance required |
| DeepSeek Harness 0.1.1-rc.2 | legacy prerelease | Isolate `CallId`, Code Mode and legacy transport names |
| DeepSeek Harness 0.1.2-alpha.1 | official prerelease | Remote gateway, one-time token, `dsh profile`, PTC Mode, `ToolCallId`, per-subagent model spec |

`ToolCallId`, `ToolPresentationMode`, `TransportKind`, `InstructionEnvelope` and `ProtocolCapabilities` are Elmos-owned canonical types. Upstream names are adapter-private.
