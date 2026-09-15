# Architecture — Engineering Control Plane v3.2

```text
Ingress (IDE/Web/CLI/CI/MCP/ACP/A2A)
          |
          v
Authority Plane
 Identity | Policy | Approval | Secrets | CapabilityLease
          |
          v
Work Plane
 Program -> CertificationWorkPackage DAG -> Durable Workflow
          |
          v
Runtime Plane
 AgentRuntimeAdapter + RuntimeOwner + CapabilityNegotiation
          |
          v
Execution Fabric
 Local/Container/K8s/ECS/Cloud workers + leases/fencing
          |
          v
Workspace & Result Plane
 Managed Worktree -> Candidate Checkpoint -> ResultFence
          |
          v
Assurance Plane
 VerificationTicket -> Truth Runner -> Evidence -> OPA -> Certifier
          |
          v
Publication Plane
 CertifiedCheckpoint -> PublicationBroker -> DeploymentBroker
```

Cross-cutting: Repository Semantic Compiler, TypedContext/Provenance, ExecutionTimeline, ArtifactStore, Skill Registry, Versioned State, OTel, Audit Ledger.

## Core execution model

`Execution = Identity + Ownership + TypedContext + Timeline + Artifacts + Policy + Lifecycle + Effects`

### Ownership is not lineage
`parent_execution_id` explains ancestry; `RuntimeOwner` controls who may continue/recover/write the live execution. A child cannot cold-resume itself from a stale snapshot if its runtime owner is unavailable.

### Capability inventory is not readiness
A registered MCP/tool capability may exist while transport is failed or authentication-required. `observeRuntimeStatus()` is side-effect free; connection is a separate control operation.

### Policy composition
`EffectivePolicy = intersection(TenantPolicy, HarnessPolicy, EnvironmentPolicy, ToolPolicy)`.
Hard denies are monotonic; approval or escalation cannot override an environment-owner deny.

### Context is typed data
Context carries semantic kind, producer, trust, scope, retention and replay rules. Merge/truncate/compact/fork/model-switch MUST preserve provenance and child/root scope.

### Timeline is the fact source
Messages are a view. Durable `ExecutionTimeline` + typed artifacts are the replay source; UI/history/reports are projections.
