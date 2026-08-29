---
name: data-lineage-impact-analysis
version: 1.0.0
priority: P0
kernel: K7-database-data
kind: production-skill
---

# data-lineage-impact-analysis

## Objective
Track run/job/dataset/table/column lineage so code/schema changes propagate to affected pipelines and consumers.

## Inspirations
- OpenLineage
- DataHub patterns

## Activation conditions
- Activate when the task requires: track run/job/dataset/table/column lineage so code/schema changes propagate to affected pipelines and consumers.
- Activate automatically when the risk/evidence planner marks this capability as mandatory.
- Do not activate solely because an upstream tool is installed; capability need and policy must match.

## Required inputs
- `TaskContext`: tenant, repository, branch/revision, task goal, constraints and budget.
- `RepositoryEvidence`: semantic/build/runtime/data graph references when relevant.
- `PolicyDecision`: allowed tools, files, network, secrets, models and execution tier.
- `EvidenceObligations`: required E0-E5 gates and acceptance thresholds.

## Workflow
1. Discover source/target database semantics and metadata.
2. Lift schema/query/routine behavior into Database IR.
3. Transform with explicit target capability checks.
4. Run structural/data/runtime/performance differential validation.
5. Produce reconciliation, lineage and rollback evidence.

## Required outputs
- Machine-readable result with status, confidence and unresolved assumptions.
- Evidence references sufficient to reproduce or audit the result.
- Declared side effects and rollback/recovery metadata where side effects exist.
- Metrics for wall-clock duration, compute/token cost and cache effectiveness where applicable.

## Production invariants
- Deterministic/replayable execution where applicable.
- Fail-closed on missing mandatory evidence.
- Tenant and secret isolation.
- Machine-readable result + provenance.
- Regression coverage for every discovered failure.

## Integration contracts
- Reads/writes only through Elmos normalized IR/graph/evidence interfaces when an interface exists.
- Emits OpenTelemetry-compatible trace identity and links child tool/build/test executions.
- Persists source/tool/skill/model versions into provenance for any releasable artifact.
- Surfaces uncertainty; never convert an unsupported semantic construct into a guessed equivalent silently.

## Certification
- Unit fixtures for deterministic logic.
- Golden-route repository fixtures for integration behavior.
- Failure-injection fixture proving fail-closed or safe rollback behavior.
- At least one regression fixture for every production defect attributed to this skill.
