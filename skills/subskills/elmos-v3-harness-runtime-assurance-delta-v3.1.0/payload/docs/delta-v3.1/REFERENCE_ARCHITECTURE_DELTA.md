# Reference Architecture Delta v3.1

## Refined execution equation

```text
Execution = Identity
          + Ownership
          + Environment
          + LeasedCapabilities
          + VerifiedAuthority
          + TypedIngress
          + Timeline
          + Artifacts
          + Lifecycle
          + CommittedEffects
```

```text
Step = ModelSnapshot
     + EnvironmentSnapshot
     + AuthoritySnapshot
     + FinalizedCapabilities
     + Lifecycle
     + CommittedEffects
```

## Tool result commit boundary

```text
server result
  → RAW_RESULT_CAPTURED
  → ordered RESULT_INTERCEPT chain
  → immutable identity verification
  → RESULT_COMMIT
  → completion event + model input + downstream evidence
```

The journal stores `rawResult`, `effectiveResult`, `interceptorChain`, `mutationProvenance`, exact authority/environment/plan identities and terminal error semantics.

## Ownership hierarchy

```text
Goal / Run
  └─ Execution Epoch
      └─ Step ExecutionPlan
          ├─ Environment owner
          │   ├─ Attachment/MCP authority
          │   └─ Executor generation / connection epoch
          ├─ Workspace owner / generation
          ├─ Invocation CapabilityLease
          └─ Result Commit
```

No ToolCall derives authority from a mutable session-global field.
