---
name: elmos-commercial-capability-expansion
version: 2.0.0
priority: P0
kind: meta-skill
---

# Elmos Commercial Capability Expansion

## Trigger
Use for repository generation, modernization, cross-language conversion, SQL/database migration, repository refactoring, certification, deployment readiness, or any long-running coding task where commercial-production guarantees are required.

## Mandatory orchestration
1. Build repository semantic context before planning edits.
2. Compute risk and required evidence obligations.
3. Prefer deterministic transformations; use LLM generation only for semantic gaps.
4. Execute user code only through the risk-selected sandbox/runtime lab.
5. Validate behavior with affected tests plus risk-triggered static/dynamic/formal checks.
6. Aggregate evidence into the configured E0-E5 gate.
7. Emit provenance/SBOM/signatures for releasable artifacts.
8. Store trajectory, failures and evidence for later evaluation; never self-promote a new rule/skill directly from one production run.

## Global invariants
- No silent semantic loss.
- No untracked privileged side effect.
- No production promotion with stale/missing mandatory evidence.
- Every generated edit is attributable to a rule/skill/model/tool and source evidence.
- Every failure becomes a reproducible fixture when legally and technically possible.
