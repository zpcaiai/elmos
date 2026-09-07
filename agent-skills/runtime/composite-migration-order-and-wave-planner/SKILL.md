---
name: composite-migration-order-and-wave-planner
description: Generate contract-aware cross-repository migration order and waves using topology, data ownership, business risk, capacity, and rollback evidence. Use after landscape and contract baselining.
---

# Composite Migration Order and Wave Planner

## Rules

Do not assume producer-first or consumer-first. Choose producer-first only with backward compatibility; consumer-first when consumers must learn both formats; use lockstep or a bridge for non-compatible transaction, protocol, or shared-data coupling.

## Workflow

1. Build the directed dependency graph and compress strongly connected components into composite migration units.
2. Apply `MUST_PRECEDE`, `MUST_FOLLOW`, `MUST_MIGRATE_WITH`, `MUST_NOT_OVERLAP`, `REQUIRES_COMPATIBILITY_WINDOW`, `REQUIRES_DATA_SYNC`, and `REQUIRES_EXTERNAL_CONSUMER` constraints.
3. Apply data-authority order, critical path, business risk, release windows, rollback readiness, and team capacity.
4. Produce Wave 0 observability/contracts; Wave 1 compatibility foundation; Wave 2 low-risk consumers; Wave 3 producers/core services; Wave 4 data ownership; Wave 5 high-risk core; Wave 6 compatibility removal/decommission.
5. Trace every system step to repository-level Java, .NET, or Python engine plans. Never synthesize source-edit tasks here.

## Gate

Block on incomplete contract matrices, unknown consumers, shared database coupling without a data plan, unresolved SCCs, or missing repository-plan traceability.
