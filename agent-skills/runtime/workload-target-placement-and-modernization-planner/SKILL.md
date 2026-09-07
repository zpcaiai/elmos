---
name: workload-target-placement-and-modernization-planner
description: Select and explain VM, container, Kubernetes, serverless, managed, edge, retire, or replacement targets from workload evidence, hard constraints, team readiness, cost, and portability. Use for infrastructure placement and migration DAGs.
---

# Workload Placement Planner

## Planning workflow

1. Require an immutable workload profile and evidence for state, startup, duration, traffic, scale, storage, network, hardware, OS, license, middleware, availability, latency, security, compliance, team readiness, cost, and portability.
2. Compare keep-and-harden, VM rehost/replatform, container-on-VM/platform, Kubernetes, serverless container, function, managed service, edge, retire, and replace-product candidates.
3. Treat hardware, OS, state, residency, latency, and licensing as hard constraints where applicable.
4. Score feasible candidates and preserve alternatives, reason codes, required refactors, validation gates, confidence, and unknowns.
5. Select rehost, replatform, repackage, refactor, rearchitect, replace, or retire strategy.
6. Produce a dependency-aware migration DAG and target profile covering runtime, region/zone, compute, storage, network, identity, secrets, scaling, availability, backup, observability, cost budget, and portability.

Do not rank Kubernetes highest by default. Recommend serverless only when duration, cold start, state, idempotency, concurrency, connections, and cost are compatible. Account for the customer's operational capability.

Return `PILOT_REQUIRED`, `BLOCKED`, or `UNKNOWN` instead of manufacturing certainty. Every recommendation must be reproducible from versioned inputs and weights.

