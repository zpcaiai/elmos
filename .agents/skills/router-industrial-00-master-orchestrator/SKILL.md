---
name: "router-industrial-00-master-orchestrator"
implementation_state: "VERIFIED"
external_evidence_status: "LOCAL_EXECUTED"
production_certification: "NOT_CERTIFIED"
description: "Coordinate end-to-end routing plane execution, migration, and feature-flagged coexistence."
metadata:
  source_package: "elmos-router-industrial-skillpack"
  source_package_id: "elmos.router-industrial-skillpack"
  source_version: "1.0.0"
  source_path: "skills/00-master-orchestrator/SKILL.md"
  source_sha256: "sha256:e3748be778adfe7ea465f7169400ed5c56d2a5019d1656048c734f56b791f7f3"
  normalized_namespace: "router-industrial-v1"
  runtime_module: "engines/router-industrial-engine/src/elmos_router_industrial/skill_runtime.py"
  runtime_dispatcher: "dispatch_skill"
  runtime_skill_key: "router-industrial-00-master-orchestrator"
  runtime_handler: "execute_00_master_orchestrator"
  runtime_phase: "orchestration"
  runtime_evidence: "LOCAL_EXECUTED"
  external_evidence: "NOT_RUN"
  certification: "READY_FOR_RAMPING"
---

## Trusted Repository Runtime Wrapper

This installed Skill is a repository-owned dispatch interface for `router-industrial-00-master-orchestrator`.
The extracted source mirror in `skills/elmos-router-industrial-skillpack/` provides specification and configuration data.
Execution is strictly mediated by the typed repository engine `engines/router-industrial-engine`.

### Invocation Contract

1. Accept structured requests for exact Skill key `router-industrial-00-master-orchestrator`.
2. Dispatch only through `engines/router-industrial-engine/src/elmos_router_industrial/skill_runtime.py` / `dispatch_skill` to `execute_00_master_orchestrator`.
3. Enforce 15 hard policy filters, fail-closed residency checks, token bucket rate limiting, hierarchical budgets, and CAS idempotency.
4. Redact API keys, tokens, and credentials from all prompts, traces, and metrics before egress or persistence.
5. All external vendor calls remain bounded, monitored, circuit-broken, and fallback-eligible.

---

### Source Specification Reference

```markdown
# Skill 00 — Master Orchestrator

## Goal
Coordinate all routing-plane work as a controlled migration, not a big-bang rewrite.

## Tasks
1. Inventory existing model/provider calls, including hidden direct HTTP calls.
2. Identify task/step identifiers, durable events, billing, auth, permission context, and trace context.
3. Produce a dependency map:
   `caller -> routing -> adapter -> provider -> result commit`.
4. Create feature flags:
   - `router_v2_enabled`
   - `shadow_route_enabled`
   - `native_lane_enabled`
   - `openrouter_fallback_enabled`
5. Define coexistence:
   legacy path remains callable until certification gates pass.
6. Freeze package/module boundaries before implementation.

## Acceptance
- All known model calls are inventoried.
- No new provider call bypasses the new SPI.
- Rollback to legacy route requires configuration only.
```
