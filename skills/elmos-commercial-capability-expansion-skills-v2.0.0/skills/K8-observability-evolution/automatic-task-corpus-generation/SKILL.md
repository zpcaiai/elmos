---
name: automatic-task-corpus-generation
version: 1.0.0
priority: P1
kernel: K8-observability-evolution
kind: production-skill
---

# automatic-task-corpus-generation

## Objective
Generate diverse, adversarial and boundary tasks from environments and failure clusters to expand certification/training corpora.

## Inspirations
- AgentEvolver self-questioning

## Activation conditions
- Activate when the task requires: generate diverse, adversarial and boundary tasks from environments and failure clusters to expand certification/training corpora.
- Activate automatically when the risk/evidence planner marks this capability as mandatory.
- Do not activate solely because an upstream tool is installed; capability need and policy must match.

## Required inputs
- `TaskContext`: tenant, repository, branch/revision, task goal, constraints and budget.
- `RepositoryEvidence`: semantic/build/runtime/data graph references when relevant.
- `PolicyDecision`: allowed tools, files, network, secrets, models and execution tier.
- `EvidenceObligations`: required E0-E5 gates and acceptance thresholds.

## Workflow
1. Instrument the full run with stable semantic identifiers.
2. Aggregate trajectories/evidence/outcomes into versioned datasets.
3. Evaluate failures and improvement candidates offline.
4. Canary changes under strict rollback thresholds.
5. Promote only measurable improvements and retain lineage.

## Required outputs
- Machine-readable result with status, confidence and unresolved assumptions.
- Evidence references sufficient to reproduce or audit the result.
- Declared side effects and rollback/recovery metadata where side effects exist.
- Metrics for wall-clock duration, compute/token cost and cache effectiveness where applicable.

## Production invariants
- Versioned configuration and evaluation corpus.
- No silent fallback that weakens guarantees.
- Auditable inputs/outputs and failure classification.

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
