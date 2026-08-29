---
name: repository-semantic-code-graph
version: 1.0.0
priority: P0
kernel: K2-repository-intelligence
kind: production-skill
---

# repository-semantic-code-graph

## Objective
Fuse syntax, symbol, type, call, inheritance, dependency, build, data and runtime evidence into one queryable repository graph.

## Inspirations
- SCIP
- Tree-sitter
- OpenTelemetry

## Activation conditions
- Activate when the task requires: fuse syntax, symbol, type, call, inheritance, dependency, build, data and runtime evidence into one queryable repository graph.
- Activate automatically when the risk/evidence planner marks this capability as mandatory.
- Do not activate solely because an upstream tool is installed; capability need and policy must match.

## Required inputs
- `TaskContext`: tenant, repository, branch/revision, task goal, constraints and budget.
- `RepositoryEvidence`: semantic/build/runtime/data graph references when relevant.
- `PolicyDecision`: allowed tools, files, network, secrets, models and execution tier.
- `EvidenceObligations`: required E0-E5 gates and acceptance thresholds.

## Workflow
1. Discover repository languages/build systems/components.
2. Build or update semantic indexes and graphs.
3. Resolve uncertainty using compiler/runtime evidence.
4. Produce impact/context/test slices with confidence scores.
5. Persist graph deltas and provenance for downstream planning.

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
