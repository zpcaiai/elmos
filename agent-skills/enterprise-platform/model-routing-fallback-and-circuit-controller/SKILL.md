---
name: model-routing-fallback-and-circuit-controller
description: Route and fail over models by policy, required capability, quality, availability, latency, and cost with bounded retry and circuit breaking. Use for model routing, fallback, reproducibility, or outage behavior.
---

# Model Routing Fallback and Circuit Controller

Read `../references/batch-12-enterprise-platform.md`. Evaluate policy first, record each attempted exact model separately and bound retries, budget and circuit half-open recovery. Disable automatic fallback for fixed-model, high-risk, denied, budget-exhausted or suspicious-output tasks.

Fallback can never relax data classification, residency or provider rules. A violating route blocks T-D.
