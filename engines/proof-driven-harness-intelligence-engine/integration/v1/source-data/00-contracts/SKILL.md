---
name: elmos-harness-contracts
description: Canonical contracts shared by all Elmos proof-driven harness kernels.
---

# K0 — Contracts

## Required contracts

1. `AgentTask` — bounded unit of agent work.
2. `ProofCarryingAgentResult` — typed result with evidence and unresolved risk.
3. `PatchTransaction` — mutation contract.
4. `RuleIR` — normalized enterprise rule/invariant.
5. `EvidenceRecord` — provenance-bearing evidence.
6. `DurableJobState` — restart-safe job state.
7. `CertificationBundle` — E0–E5 evidence package.
8. `SkillManifest` — versioned skill lifecycle metadata.

## Cross-cutting invariants

- IDs MUST be stable and globally unique inside a project job.
- Every mutation MUST reference an input revision.
- Every evidence item MUST reference producer, timestamp, inputs, tool/runtime version, and artifact digest.
- Every pass/fail verdict MUST name the evidence ids it relies on.
- Every failure MUST be classifiable as transient, deterministic, policy, semantic, infrastructure, provider, quota, or unknown.
- Unknown failures MUST NOT be auto-promoted to success.
- Retry MUST preserve idempotency keys and side-effect fences.
