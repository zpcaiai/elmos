# Kernel Integration

The package is organized into eight implementation domains. These are **capability domains**, not separate microservices; deploy boundaries should follow scaling/security needs.

| Domain | Responsibility | Core persisted artifacts |
|---|---|---|
| K1 Skill Runtime | discovery, routing, orchestration, checkpointing | SkillVersion, TaskRun, Checkpoint, ToolCall |
| K2 Repository Intelligence | syntax/symbol/build/runtime/ownership graph | Symbol, Edge, Target, RuntimeLink, ContextSlice |
| K3 Transformation | IR, rewrite routing, migration ledger | TransformPlan, Edit, Assumption, RollbackMap |
| K4 Build & Execution | hermetic/sandbox/native execution | EnvironmentSnapshot, BuildRun, CacheKey, RuntimeRun |
| K5 Verification | tests, fuzz, differential, formal, E0-E5 | TestRun, Counterexample, ProofResult, GateDecision |
| K6 Security & Governance | policy, authorization, secrets, supply chain | PolicyDecision, Attestation, SBOM, Signature |
| K7 Database & Data | DB IR, dialect/routine/data migration, lineage | SchemaIR, SqlIR, Reconciliation, LineageEdge |
| K8 Observability & Evolution | traces, evals, datasets, skill promotion | Trace, DatasetVersion, EvalRun, PromotionDecision |

## Cross-kernel mandatory flow

`Task -> Policy -> Repository Graph -> Risk/Evidence Plan -> Transformation -> Sandboxed Build/Run -> Verification -> Evidence Bundle -> E0-E5 Decision -> Artifact/Provenance -> Trajectory Dataset`

No kernel may bypass Policy or Evidence just because a task is small; the planner may choose lightweight obligations, but the decision must still be explicit.
