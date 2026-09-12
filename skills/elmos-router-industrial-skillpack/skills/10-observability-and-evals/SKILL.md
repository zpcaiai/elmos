# Skill 10 — Observability, Health & Evals

## Goal
Know why a route was chosen, how it behaved, how much it cost, and whether it improved Elmos outcomes.

## OpenTelemetry spans
Recommended:
- `elmos.route.evaluate`
- `elmos.route.select`
- `elmos.gateway.invoke`
- `elmos.provider.invoke`
- `elmos.provider.stream`
- `elmos.result.validate`
- `elmos.result.commit`

Attributes:
- tenant pseudonymous id
- taskClass
- modelAlias
- provider/deployment
- lane
- routeDecisionId
- policyVersion
- registryVersion
- attempt
- fallbackIndex
- status/errorClass
- token counts
- cost
- latency
- cache hit
- prompt hash, not prompt body

## Metrics
At minimum:
- request rate
- success/error by class
- p50/p95/p99 latency
- TTFT
- tokens/sec where available
- fallback rate
- retry rate
- circuit-open count
- budget denials
- cost per tenant/task/model
- route distribution
- structured-output validation failure
- tool-call protocol failure
- provider health

## Health model
Do not use a single boolean.
Track windowed:
- availability
- rate-limit pressure
- timeout rate
- p95 latency
- success rate
- refusal/error classes.

## Evals
Create Elmos task-class benchmark suites:
- compilation success
- test pass
- semantic equivalence
- mutation score
- patch acceptance
- architecture rubric
- hallucination/unsupported edit rate
- wall-clock
- token/cost

Do not update routing weights directly from a single online sample. Promote benchmark versions through review.

## Acceptance
- every production request is traceable end-to-end.
- no prompt bodies appear in default telemetry.
- route-quality regression can be detected by benchmark gate.
