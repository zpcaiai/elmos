# 05 — Domain Model and Ledger Architecture

| Entity | Purpose |
|---|---|
| EngagementCase | Customer phase, stakeholders, outcomes, scope and access |
| BusinessWorkflow | Observed current/future process, exceptions and handoffs |
| RepositorySnapshot / RevisionSet | Immutable source identity and custody |
| EnvironmentFingerprint | Exact runtime/toolchain/service identity |
| SupportProfile | S0–S5 and E0–E3 coverage plus unknown/unsupported |
| UnifiedSystemGraph | Business/code/data/event/permission/deployment graph |
| IssueFinding | Evidence-backed normalized problem |
| UnknownRegister | Unresolved material questions and blockers |
| InvariantContract | Behavior/data/security/operational property to preserve |
| TargetArchitecture / ADR | Alternatives, decision, consequences and exit |
| TransformationPlan / Step | Executable DAG, scope, obligations and estimates |
| ChangeSet | Atomic reversible change and provenance |
| EvidenceArtifact / Claim | Version-bound proof and explicit assertion |
| SideEffectRecord | Authorized effects, idempotency and compensation |
| RiskWaiver | Time-bounded independent risk acceptance |
| CustomerAcceptance | Criterion-by-criterion customer review |

## Ledgers

- **Evidence Ledger**: raw and derived evidence, identity, freshness and counterexamples.
- **Claim Ledger**: proposed/supported/refuted/unknown/waived statements.
- **Change Ledger**: plan, ChangeSet, files, provenance and revert.
- **Effect Ledger**: external or durable effects, idempotency and compensation.
- **Decision Ledger**: scope, architecture, waiver, acceptance and K8 decisions.

Ledgers are append-only, tenant-scoped, hash-chained and projected into query models. Corrections append superseding events; history is not silently rewritten.
