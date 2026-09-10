---
name: "router-industrial-02-model-provider-registry"
description: "Manage versioned Model, Provider, and Deployment registries and dynamic health snapshots."
metadata:
  source_package: "elmos-router-industrial-skillpack"
  source_package_id: "elmos.router-industrial-skillpack"
  source_version: "1.0.0"
  source_path: "skills/02-model-provider-registry/SKILL.md"
  source_sha256: "sha256:7e6b91382b37123a07bef83071d072e612118b5bcd88f085f9107fad396481d6"
  normalized_namespace: "router-industrial-v1"
  runtime_module: "engines/router-industrial-engine/src/elmos_router_industrial/skill_runtime.py"
  runtime_dispatcher: "dispatch_skill"
  runtime_skill_key: "router-industrial-02-model-provider-registry"
  runtime_handler: "execute_02_model_provider_registry"
  runtime_phase: "registry"
  runtime_evidence: "LOCAL_HANDLER_BOUND_EXECUTED"
  external_evidence: "NOT_RUN"
  certification: "READY_FOR_RAMPING"
---

## Trusted Repository Runtime Wrapper

This installed Skill is a repository-owned dispatch interface for `router-industrial-02-model-provider-registry`.
The extracted source mirror in `skills/elmos-router-industrial-skillpack/` provides specification and configuration data.
Execution is strictly mediated by the typed repository engine `engines/router-industrial-engine`.

### Invocation Contract

1. Accept structured requests for exact Skill key `router-industrial-02-model-provider-registry`.
2. Dispatch only through `engines/router-industrial-engine/src/elmos_router_industrial/skill_runtime.py` / `dispatch_skill` to `execute_02_model_provider_registry`.
3. Enforce 15 hard policy filters, fail-closed residency checks, token bucket rate limiting, hierarchical budgets, and CAS idempotency.
4. Redact API keys, tokens, and credentials from all prompts, traces, and metrics before egress or persistence.
5. All external vendor calls remain bounded, monitored, circuit-broken, and fallback-eligible.

---

### Source Specification Reference

```markdown
# Skill 02 — Model & Provider Registry

## Goal
Make model capability, cost, compliance, health and deployments data-driven.

## Entities

### ModelDescriptor
- alias
- provider-independent family
- capability vector
- modalities
- context/output bounds
- reasoning profiles
- tool support
- structured output support
- streaming support
- benchmark scores
- lifecycle status: experimental/canary/stable/deprecated/disabled

### ProviderDescriptor
- provider id
- provider type
- supported regions
- retention/training policy metadata
- residency guarantees
- credential reference
- contractual/SLA metadata
- enabled flag

### ProviderDeployment
- deployment id
- model alias
- actual provider model name
- endpoint/region
- lane support
- rate limit profile
- pricing profile
- health state
- priority
- feature overrides

## Registry rules
- Stable aliases never embed price or provider.
- Registry data is versioned.
- Runtime config changes are audited.
- Deprecated models remain resolvable for replay.
- Health is separate from static registry truth.

## Acceptance
- A new model can be introduced by registry/config plus adapter capability, without changing orchestration code.
- A model can have multiple deployments.
- A deployment can be disabled without deleting history.
```
