# Reference Architecture

```text
CLI / Web / IDE / API / GitHub App
                 │
        eLMOS Control Plane
     Java 21 + Spring Boot
                 │
 ┌───────────────┼────────────────────┐
 │               │                    │
Temporal      Policy/Budget       OpenFeature
Workflow      OPA / Quota         Rule/Model Flags
 │               │                    │
 └───────────────┼────────────────────┘
                 │
        Action Graph / Scheduler
                 │
 ┌───────────────┼───────────────────────────────┐
 │               │               │               │
Parse/Index   Semantic IR     Generate/Repair  Validate
Tree-sitter  Compiler APIs    Rule + LLM       Build/Test
Incremental  Canonical IR     Templates        Diff/Fuzz
 │               │               │               │
 └───────────────┴───────────────┴───────────────┘
                 │
          Runner Execution Fabric
 Native / Rootless OCI / K8s / External / Windows / macOS / GPU
                 │
   gVisor / Firecracker / Kata / Wasmtime where required
                 │
 ┌───────────────┼───────────────────────────────┐
 │               │               │               │
L1 Local CAS   Shared CAS      PostgreSQL     Arrow/Parquet
NVMe Cache     S3/MinIO        Authority      Analytics
                 │
  OpenTelemetry Trace + Metric + Log + Profile + Cost
```

## Authority boundaries

| System | Authority |
|---|---|
| PostgreSQL | Users, tenants, memberships, projects, task projections, metadata, references, budgets, audit |
| Temporal | Durable long-running workflow history and orchestration |
| CAS/Object Storage | Immutable source/IR/action/artifact/log/evidence bytes addressed by digest |
| Runner local cache | Evictable optimization only |
| Redis | Short-lived hot hints, rate limits, sessions; never sole workflow/task/artifact authority |
| Event bus | Broadcast/replay/integration; not the workflow state machine |
| Policy engine | Versioned decisions; source policy remains signed/versioned configuration |
| Evidence Pack | Portable immutable delivery proof, independently verifiable |

## Mandatory cross-cutting properties

- Authenticated identity and tenant/resource authorization.
- Per-task idempotency, fencing, cancellation, checkpoint and reconciliation.
- Immutable input, toolchain, rule/model/policy and output identity.
- Default source-local private execution and explicit export.
- Deterministic rule/compiler path before agent repair.
- Verification and Evidence Pack before promotion.
- End-to-end telemetry, cost, machine wall-clock ETA, audit and recovery.
