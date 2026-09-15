# AgentRuntimeAdapter SPI v3.2

Required operations:

- `getProtocolVersion()`
- `getSupportedCapabilities()`
- `getSupportedApprovalModes()`
- `validatePolicyMapping(effectivePolicy)` — MUST fail closed on unmappable hard-deny or approval semantics.
- `observeRuntimeStatus(threadId)` — observation MUST NOT start, reconnect or authenticate a runtime.
- `createSession(SessionInheritancePolicy)`
- `createInternalSession(ExecutionSource, parentExecutionId, historyMode)`
- `execute(finalizedExecutionPlan, capabilityLease)`
- `quiesce(executionId)`
- `checkpoint(executionId)`
- `handoff(executionId, targetOwner)`
- `resumeSameExecutionId(executionId, runtimeOwner)`
- `interrupt(executionId)`
- `ingestToolResult(toolResultEnvelope)`
- `exportRuntimeEvidence(executionId)`

Negotiation result is exactly one of `SUPPORTED_EXACTLY`, `SUPPORTED_WITH_NARROWER_SCOPE`, `UNSUPPORTED`; there is no security-relevant `BEST_EFFORT` success state.
