---
name: contract-compatibility-verification
version: 1.0.0
priority: P0
kernel: K5-verification
kind: production-skill
---

# contract-compatibility-verification

## Objective
Verify consumer/provider compatibility across language boundaries and prevent breaking service/event contract changes.

## Inspirations
- Pact

## Activation conditions
- Activate when the task requires: verify consumer/provider compatibility across language boundaries and prevent breaking service/event contract changes.
- Activate automatically when the risk/evidence planner marks this capability as mandatory.
- Do not activate solely because an upstream tool is installed; capability need and policy must match.

## Required inputs
- `TaskContext`: tenant, repository, branch/revision, task goal, constraints and budget.
- `RepositoryEvidence`: semantic/build/runtime/data graph references when relevant.
- `PolicyDecision`: allowed tools, files, network, secrets, models and execution tier.
- `EvidenceObligations`: required E0-E5 gates and acceptance thresholds.

## Workflow
1. Derive required verification obligations from change risk.
2. Generate/select minimal high-value tests and oracles.
3. Execute in native/hermetic environments.
4. Minimize and classify failures; feed repair loop.
5. Emit signed evidence and gate decision.

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
