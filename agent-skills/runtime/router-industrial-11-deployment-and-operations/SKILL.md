---
name: "router-industrial-11-deployment-and-operations"
implementation_state: "VERIFIED"
external_evidence_status: "LOCAL_EXECUTED"
production_certification: "NOT_CERTIFIED"
description: "Validate deployment readiness, health probes, zero-downtime reconfiguration, and graceful drain."
metadata:
  source_package: "elmos-router-industrial-skillpack"
  source_package_id: "elmos.router-industrial-skillpack"
  source_version: "1.0.0"
  source_path: "skills/11-deployment-and-operations/SKILL.md"
  source_sha256: "sha256:42fa50bfc03d0599db838cd1d1ff0907a12015184c2e8a4fdccbd34b043b9adb"
  normalized_namespace: "router-industrial-v1"
  runtime_module: "engines/router-industrial-engine/src/elmos_router_industrial/skill_runtime.py"
  runtime_dispatcher: "dispatch_skill"
  runtime_skill_key: "router-industrial-11-deployment-and-operations"
  runtime_handler: "execute_11_deployment_and_operations"
  runtime_phase: "operations"
  runtime_evidence: "LOCAL_EXECUTED"
  external_evidence: "NOT_RUN"
  certification: "READY_FOR_RAMPING"
---

## Trusted Repository Runtime Wrapper

This installed Skill is a repository-owned dispatch interface for `router-industrial-11-deployment-and-operations`.
The extracted source mirror in `skills/elmos-router-industrial-skillpack/` provides specification and configuration data.
Execution is strictly mediated by the typed repository engine `engines/router-industrial-engine`.

### Invocation Contract

1. Accept structured requests for exact Skill key `router-industrial-11-deployment-and-operations`.
2. Dispatch only through `engines/router-industrial-engine/src/elmos_router_industrial/skill_runtime.py` / `dispatch_skill` to `execute_11_deployment_and_operations`.
3. Enforce 15 hard policy filters, fail-closed residency checks, token bucket rate limiting, hierarchical budgets, and CAS idempotency.
4. Redact API keys, tokens, and credentials from all prompts, traces, and metrics before egress or persistence.
5. All external vendor calls remain bounded, monitored, circuit-broken, and fallback-eligible.

---

### Source Specification Reference

```markdown
# Skill 11 — Deployment & Operations

## Goal
Deploy the routing plane as an HA, independently scalable production subsystem.

## Services
Recommended logical components:
- Elmos Router API/library
- Model Registry/Policy service or module
- LiteLLM Proxy cluster
- provider adapter workers if isolation is desired
- telemetry collector
- PostgreSQL
- optional Redis

Keep initial deployment simpler if possible; preserve logical boundaries even if some modules share a process.

## HA
- >=2 instances for stateless router/gateway
- multi-AZ where platform supports it
- readiness based on local health, not every provider being up
- graceful drain for streaming requests
- bounded shutdown
- connection pool protection
- DB migrations backward-compatible

## Configuration rollout
- draft -> validate -> canary -> active
- immutable version ids
- instant rollback to prior active version
- reject invalid model capability/policy combinations before activation

## Secret rotation
- credentials referenced by secret id
- adapter resolves latest valid secret at call time or short TTL cache
- dual-key rotation where providers permit
- rotation does not require app redeploy

## SLO starting targets
Treat these as initial engineering targets to validate in staging, not universal guarantees:
- route decision p95 < 25 ms excluding external calls
- router availability >= 99.95%
- no single gateway dependency for native-capable strategic routes
- 100% inference attempts have trace id and cost attribution
- 0 plaintext provider secrets in logs/events

## Acceptance
- rolling deploy preserves active streams or drains them safely.
- gateway outage leaves eligible native lane functional.
- config rollback tested.
```
