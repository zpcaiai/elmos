---
name: "router-industrial-04-routing-engine"
implementation_state: "VERIFIED"
external_evidence_status: "LOCAL_EXECUTED"
production_certification: "NOT_CERTIFIED"
description: "Compute 4-phase deterministic route decisions, multi-factor scoring, and fallback sequences."
metadata:
  source_package: "elmos-router-industrial-skillpack"
  source_package_id: "elmos.router-industrial-skillpack"
  source_version: "1.0.0"
  source_path: "skills/04-routing-engine/SKILL.md"
  source_sha256: "sha256:c1bf1b183b17ef91efe6f67577a0dfa9bdad62236837016d7c3576c06c2c0ecc"
  normalized_namespace: "router-industrial-v1"
  runtime_module: "engines/router-industrial-engine/src/elmos_router_industrial/skill_runtime.py"
  runtime_dispatcher: "dispatch_skill"
  runtime_skill_key: "router-industrial-04-routing-engine"
  runtime_handler: "execute_04_routing_engine"
  runtime_phase: "routing"
  runtime_evidence: "LOCAL_EXECUTED"
  external_evidence: "NOT_RUN"
  certification: "READY_FOR_RAMPING"
---

## Trusted Repository Runtime Wrapper

This installed Skill is a repository-owned dispatch interface for `router-industrial-04-routing-engine`.
The extracted source mirror in `skills/elmos-router-industrial-skillpack/` provides specification and configuration data.
Execution is strictly mediated by the typed repository engine `engines/router-industrial-engine`.

### Invocation Contract

1. Accept structured requests for exact Skill key `router-industrial-04-routing-engine`.
2. Dispatch only through `engines/router-industrial-engine/src/elmos_router_industrial/skill_runtime.py` / `dispatch_skill` to `execute_04_routing_engine`.
3. Enforce 15 hard policy filters, fail-closed residency checks, token bucket rate limiting, hierarchical budgets, and CAS idempotency.
4. Redact API keys, tokens, and credentials from all prompts, traces, and metrics before egress or persistence.
5. All external vendor calls remain bounded, monitored, circuit-broken, and fallback-eligible.

---

### Source Specification Reference

```markdown
# Skill 04 — Routing Engine

## Goal
Deterministically choose the best eligible deployment for each Elmos step.

## Algorithm

### Phase A — hard eligibility
Filter with Skill 03 policies.

### Phase B — normalized scoring
For each eligible candidate compute a score from:
- capability fit
- task-specific benchmark quality
- reliability/health
- expected latency
- estimated cost
- cache affinity
- region affinity
- provider diversity
- historical task-class success

Recommended structure:

`score = Σ(weight_i * normalized_feature_i) - penalties`

Never encode policy denial as a low score.

### Phase C — tie-break
Stable deterministic tie-break:
1. higher policy priority
2. lower projected cost
3. higher health
4. stable deployment id lexical order

### Phase D — fallback graph
Generate ordered fallbacks with constraints:
- same required capabilities;
- no compliance weakening;
- no budget bypass;
- provider diversity preferred;
- avoid repeatedly selecting same outage domain;
- preserve native lane if required.

## Task classes
Start with Elmos-specific classes:
- REPO_ANALYSIS
- ARCHITECTURE_REASONING
- CODE_GENERATION
- LARGE_REFACTOR
- MIGRATION_PLANNING
- MIGRATION_EXECUTION
- TEST_GENERATION
- DEBUGGING
- SQL_TRANSLATION
- FORMAL_VERIFICATION
- DOCUMENTATION
- CHEAP_CLASSIFICATION
- EMBEDDING
- RERANKING

## Shadow mode
For every production request, optionally compute route-v2 decision without executing it. Compare:
- selected model/provider,
- estimated cost,
- expected quality tier,
- policy differences,
- latency projection.

## Acceptance
- Given same config/health snapshot/request, decision is deterministic.
- Route decision contains score explanation.
- Policy-ineligible candidate can never win.
- Property tests cover candidate permutations.
```
