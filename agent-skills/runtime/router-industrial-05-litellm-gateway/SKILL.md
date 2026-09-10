---
name: "router-industrial-05-litellm-gateway"
description: "Interface with LiteLLM proxy as a replaceable gateway while maintaining architectural authority."
metadata:
  source_package: "elmos-router-industrial-skillpack"
  source_package_id: "elmos.router-industrial-skillpack"
  source_version: "1.0.0"
  source_path: "skills/05-litellm-gateway/SKILL.md"
  source_sha256: "sha256:6cc1bb13942d630e65b6f67e0b2a2e9c5f5122e7dea15d5086bc51178b549c99"
  normalized_namespace: "router-industrial-v1"
  runtime_module: "engines/router-industrial-engine/src/elmos_router_industrial/skill_runtime.py"
  runtime_dispatcher: "dispatch_skill"
  runtime_skill_key: "router-industrial-05-litellm-gateway"
  runtime_handler: "execute_05_litellm_gateway"
  runtime_phase: "adapters"
  runtime_evidence: "LOCAL_HANDLER_BOUND_EXECUTED"
  external_evidence: "NOT_RUN"
  certification: "READY_FOR_RAMPING"
---

## Trusted Repository Runtime Wrapper

This installed Skill is a repository-owned dispatch interface for `router-industrial-05-litellm-gateway`.
The extracted source mirror in `skills/elmos-router-industrial-skillpack/` provides specification and configuration data.
Execution is strictly mediated by the typed repository engine `engines/router-industrial-engine`.

### Invocation Contract

1. Accept structured requests for exact Skill key `router-industrial-05-litellm-gateway`.
2. Dispatch only through `engines/router-industrial-engine/src/elmos_router_industrial/skill_runtime.py` / `dispatch_skill` to `execute_05_litellm_gateway`.
3. Enforce 15 hard policy filters, fail-closed residency checks, token bucket rate limiting, hierarchical budgets, and CAS idempotency.
4. Redact API keys, tokens, and credentials from all prompts, traces, and metrics before egress or persistence.
5. All external vendor calls remain bounded, monitored, circuit-broken, and fallback-eligible.

---

### Source Specification Reference

```markdown
# Skill 05 — LiteLLM Gateway Integration

## Goal
Use LiteLLM as a replaceable infrastructure gateway, not as the source of Elmos semantic routing truth.

## Deployment
Run LiteLLM Proxy independently from the Elmos API process.

Recommended production topology:
- >=2 proxy replicas
- health/readiness probes
- PodDisruptionBudget
- resource limits
- TLS/mTLS or trusted service mesh
- secrets through secret manager
- persistent backing DB only for features that require it
- no master key embedded in application source

## Elmos responsibilities
Elmos sends a fully resolved deployment/model alias and request policy.

## LiteLLM responsibilities
Allowed:
- protocol normalization,
- auth proxying,
- provider-compatible retries where explicitly allowed,
- provider deployment load balancing inside an Elmos-approved deployment group,
- rate limiting as defense-in-depth,
- usage/cost telemetry,
- observability hooks.

Not allowed:
- selecting a different semantic model class without Elmos permission;
- weakening retention/security policy;
- replacing Elmos budget ledger;
- changing tool permissions.

## Failover ownership
Prefer:
- Elmos owns cross-model fallback.
- LiteLLM may own same-model/same-policy deployment failover.
This avoids hidden semantic changes.

## Configuration
Use stable Elmos model aliases and explicit deployment groups.

## Acceptance
- Gateway can be bypassed by native lane for a selected deployment.
- LiteLLM outage does not take down native-direct routes.
- Elmos can reconstruct exact physical deployment used.
```
