# Architecture v2 — Adaptive Repository Planner + Cost/Performance Router

```text
Raw Requirement
  -> Requirement Normalizer
  -> Repository Intake
  -> Architecture Index
  -> Repository Intelligence Graph
  -> Implicit Requirement Miner
  -> Behavioral Scenario Graph
  -> Invariant Ledger
  -> Change Impact + Confidence
  -> Exploration (when needed)
  -> Baseline/Golden Snapshot
  -> Semantic Seam Detector
  -> Adaptive Hierarchical Planner
       goal -> capability -> changeset -> atomic task -> microstep
  -> Granularity Controller
  -> Boundary Contracts + Proof Obligations
  -> Typed Execution DAG
  -> Integration Edge Planner
  -> Plan Graph Verifier
  -> Complexity/Risk/Context
  -> 10-model Cost/Performance Router
  -> Critical Path + Resource Scheduler
  -> Isolated Worker Execution
  -> Deterministic Validation
  -> Integration + Semantic Conflict Detection
  -> Incremental Regression
  -> Dynamic Replanner (when evidence invalidates assumptions)
  -> Repository Certification
  -> Routing + Decomposition Telemetry Learning
```

## Durable run layout

```text
.elmos/runs/<run_id>/
  requirement/
  scenarios/
  rig/
  invariants/
  impact/
  exploration/
  baselines/
  plans/rev-0001.json
  plans/rev-0002.json
  dag/
  contracts/
  proofs/
  context/
  tasks/
  patches/
  evidence/
  integration/
  telemetry/
  certification/
```

## Core safety boundary

The planner may propose a task, but only the Plan Graph Verifier can mark the plan structurally executable. The router may choose a model, but only the verifier/certifier can declare the work accepted.
