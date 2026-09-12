---
name: "router-industrial-10-observability-and-evals"
implementation_state: "VERIFIED"
external_evidence_status: "LOCAL_EXECUTED"
production_certification: "NOT_CERTIFIED"
description: "Collect latency percentiles, telemetry spans with prompt redaction, and task benchmark evals."
metadata:
  source_package: "elmos-router-industrial-skillpack"
  source_package_id: "elmos.router-industrial-skillpack"
  source_version: "1.0.0"
  source_path: "skills/10-observability-and-evals/SKILL.md"
  source_sha256: "sha256:297a52d8b5e73fb26b438cdbce9c407c1f35206dbc81d6d5e1519b81b2a10ea1"
  normalized_namespace: "router-industrial-v1"
  runtime_module: "engines/router-industrial-engine/src/elmos_router_industrial/skill_runtime.py"
  runtime_dispatcher: "dispatch_skill"
  runtime_skill_key: "router-industrial-10-observability-and-evals"
  runtime_handler: "execute_10_observability_and_evals"
  runtime_phase: "observability"
  runtime_evidence: "LOCAL_EXECUTED"
  external_evidence: "NOT_RUN"
  certification: "READY_FOR_RAMPING"
---

## Trusted Repository Runtime Wrapper

This installed Skill is a repository-owned dispatch interface for `router-industrial-10-observability-and-evals`.
The extracted source mirror in `skills/elmos-router-industrial-skillpack/` provides specification and configuration data.
Execution is strictly mediated by the typed repository engine `engines/router-industrial-engine`.

### Invocation Contract

1. Accept structured requests for exact Skill key `router-industrial-10-observability-and-evals`.
2. Dispatch only through `engines/router-industrial-engine/src/elmos_router_industrial/skill_runtime.py` / `dispatch_skill` to `execute_10_observability_and_evals`.
3. Enforce 15 hard policy filters, fail-closed residency checks, token bucket rate limiting, hierarchical budgets, and CAS idempotency.
4. Redact API keys, tokens, and credentials from all prompts, traces, and metrics before egress or persistence.
5. All external vendor calls remain bounded, monitored, circuit-broken, and fallback-eligible.

---

### Source Specification Reference

```markdown
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
```
