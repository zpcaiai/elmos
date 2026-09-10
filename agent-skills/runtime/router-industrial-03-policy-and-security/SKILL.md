---
name: "router-industrial-03-policy-and-security"
implementation_state: "VERIFIED"
external_evidence_status: "LOCAL_EXECUTED"
production_certification: "NOT_CERTIFIED"
description: "Enforce 15 hard policy filters, fail-closed data residency, security context, and secret redaction."
metadata:
  source_package: "elmos-router-industrial-skillpack"
  source_package_id: "elmos.router-industrial-skillpack"
  source_version: "1.0.0"
  source_path: "skills/03-policy-and-security/SKILL.md"
  source_sha256: "sha256:945026b4d6ae2cbfae31f58d33b22c6f50c8ed45bb91b520459e81b7ad0d6649"
  normalized_namespace: "router-industrial-v1"
  runtime_module: "engines/router-industrial-engine/src/elmos_router_industrial/skill_runtime.py"
  runtime_dispatcher: "dispatch_skill"
  runtime_skill_key: "router-industrial-03-policy-and-security"
  runtime_handler: "execute_03_policy_and_security"
  runtime_phase: "policy"
  runtime_evidence: "LOCAL_EXECUTED"
  external_evidence: "NOT_RUN"
  certification: "READY_FOR_RAMPING"
---

## Trusted Repository Runtime Wrapper

This installed Skill is a repository-owned dispatch interface for `router-industrial-03-policy-and-security`.
The extracted source mirror in `skills/elmos-router-industrial-skillpack/` provides specification and configuration data.
Execution is strictly mediated by the typed repository engine `engines/router-industrial-engine`.

### Invocation Contract

1. Accept structured requests for exact Skill key `router-industrial-03-policy-and-security`.
2. Dispatch only through `engines/router-industrial-engine/src/elmos_router_industrial/skill_runtime.py` / `dispatch_skill` to `execute_03_policy_and_security`.
3. Enforce 15 hard policy filters, fail-closed residency checks, token bucket rate limiting, hierarchical budgets, and CAS idempotency.
4. Redact API keys, tokens, and credentials from all prompts, traces, and metrics before egress or persistence.
5. All external vendor calls remain bounded, monitored, circuit-broken, and fallback-eligible.

---

### Source Specification Reference

```markdown
# Skill 03 — Policy, Data Governance & Security

## Goal
Fail closed on security/compliance before cost/quality optimization.

## Data classifications
At minimum:
- PUBLIC
- INTERNAL
- CONFIDENTIAL
- SOURCE_CODE
- SECRET_BEARING
- PII

Classification may be composite.

## Hard filters
Evaluate before ranking:
1. tenant allow/deny
2. model allow/deny
3. provider allow/deny
4. region/residency
5. retention/ZDR requirement
6. training/use-of-data requirement
7. capability requirement
8. context length
9. tool support
10. structured output support
11. secret-bearing restrictions
12. budget hard ceiling
13. provider legal/compliance restrictions
14. capability lease
15. execution authority

## Security context
Integrate with Elmos `VerifiedSecurityContext` and invocation-scoped `CapabilityLease`:
- route request stores references/hashes, not raw privileged material;
- executor re-validates lease before invocation;
- replay may not mint broader authority;
- fallback inherits all constraints.

## Prompt/logging
- raw prompt/response logging OFF by default;
- redact secret/PII fields before optional debug capture;
- debug capture must be tenant-policy gated, encrypted, TTL-bound, auditable;
- traces contain hashes/size/token metadata by default.

## OpenRouter-specific requirement
Treat provider retention/training metadata as policy inputs. Do not assume all OpenRouter providers have identical retention behavior.

## Acceptance
- A denied provider cannot re-enter via fallback.
- Missing classification on protected task causes denial or conservative route.
- Security policy has deterministic unit tests.
- Secrets are absent from structured logs and traces.
```
