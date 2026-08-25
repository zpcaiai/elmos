# Architecture

## Control plane

The control plane owns requirement normalization, repository indexing, task decomposition, DAG construction, routing, budget, scheduling, state and certification. It never lets a worker redefine its own task scope.

## Worker plane

Workers receive small, contract-bounded tasks in isolated worktrees. Their output is a patch + deterministic evidence. Workers do not merge themselves.

## Model plane

Only ten logical aliases exist. Provider-specific IDs are adapters behind the registry. This prevents orchestration logic from depending on vendor naming and makes cost/quality telemetry comparable.

## Validation plane

Validation is layered: local deterministic checks -> conditional risk gates -> optional model review -> wave regression -> full repository certification.

## Learning plane

Every execution produces telemetry keyed by model alias + task class + complexity/risk/context buckets. Routing policy uses posteriors only after sufficient samples and retains hard safety floors.

## Model-selection control plane

The UI/API model selector is a control-plane input persisted before dispatch. It is not frontend-only state. `elmos-model-selection-controller` constrains the cost/performance router, registry guard, retry/escalation controller, worker executor and final reporting. This prevents UI/backend drift and prevents a manual choice from being silently ignored.
