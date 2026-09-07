---
name: generation-batch-g19-proof-driven-generation
description: Proof Obligation、Lean、SMT、Model Checking、CEGAR与反例驱动修复，FRT G19实现级Batch规范。
version: 1.0.0
batch: G19
certificate: FA0-FA6
status: implementation-ready-specification
---

# Generation Batch G19：Proof Obligation、Lean、SMT、Model Checking、CEGAR与反例驱动修复

## 1. Mission

从：

> 可构建、可测试的多路径生成系统

推进到：

> 关键语义由可机检Proof、反例和独立Kernel形成高保证证据

本Batch必须产出可由Codex直接实施的Manifest、Schema、Runtime、API、CLI、管理端、测试、Evidence和Certificate，不允许仅停留在概念文档。

## 2. Core Capabilities

- 从IR、Rule和业务不变量生成Proof Obligation
- Leanstral仅提出证明候选，Lean Kernel为可信根
- 组合SMT、Model Checking、Symbolic和Differential Evidence
- 反例统一为Counterexample IR并驱动CEGAR/CEGIS修复
- Proof-Carrying Pack和C0–C7认证

## 3. Inputs

- G3 IR、G5 Plan、G7 Generated Code、G13–G18 Packs与Invariants

## 4. Outputs

- Proof Obligation Set
- Lean/SMT/Model Evidence
- Counterexamples
- Repair Candidates
- Proof-Carrying Packs
- Formal Certificate

## 5. Global Hard Rules

- Source repository is read-only; generation, build, tests, mutation and repair run in isolated worktrees or sandboxes.
- Models propose candidates only; compilers, type checkers, formal kernels, independent tests and runtime evidence decide acceptance.
- No silent semantic loss, fake success, empty catch, fixed return, disabled assertion or UI-only authorization is permitted.
- All R4/R5 gates are non-compensatory; a critical failure cannot be hidden by aggregate scores.
- Every authoritative output binds input digests, toolchain, policy, environment, execution and evidence lineage.
- Unknown semantics must stop, emit a typed gap, request a product decision or escalate to a human reviewer.

## 6. Skills

- **FRT-1900 — Proof Assurance Orchestrator** — [`skills/frt-1900-proof-assurance-orchestrator/SKILL.md`](../../skills/frt-1900-proof-assurance-orchestrator/SKILL.md)
- **FRT-1901 — Proof Obligation IR** — [`skills/frt-1901-proof-obligation-ir/SKILL.md`](../../skills/frt-1901-proof-obligation-ir/SKILL.md)
- **FRT-1902 — Lean Specification Generator** — [`skills/frt-1902-lean-specification-generator/SKILL.md`](../../skills/frt-1902-lean-specification-generator/SKILL.md)
- **FRT-1903 — Leanstral Candidate Adapter** — [`skills/frt-1903-leanstral-candidate-adapter/SKILL.md`](../../skills/frt-1903-leanstral-candidate-adapter/SKILL.md)
- **FRT-1904 — Lean Kernel Verifier** — [`skills/frt-1904-lean-kernel-verifier/SKILL.md`](../../skills/frt-1904-lean-kernel-verifier/SKILL.md)
- **FRT-1905 — SMT Solver Adapter** — [`skills/frt-1905-smt-solver-adapter/SKILL.md`](../../skills/frt-1905-smt-solver-adapter/SKILL.md)
- **FRT-1906 — Model Checker Adapter** — [`skills/frt-1906-model-checker-adapter/SKILL.md`](../../skills/frt-1906-model-checker-adapter/SKILL.md)
- **FRT-1907 — Symbolic Execution Adapter** — [`skills/frt-1907-symbolic-execution-adapter/SKILL.md`](../../skills/frt-1907-symbolic-execution-adapter/SKILL.md)
- **FRT-1908 — Temporal Typestate and Refinement Verifier** — [`skills/frt-1908-temporal-typestate-and-refinement-verifier/SKILL.md`](../../skills/frt-1908-temporal-typestate-and-refinement-verifier/SKILL.md)
- **FRT-1909 — Noninterference Proof Generator** — [`skills/frt-1909-noninterference-proof-generator/SKILL.md`](../../skills/frt-1909-noninterference-proof-generator/SKILL.md)
- **FRT-1910 — Counterexample IR** — [`skills/frt-1910-counterexample-ir/SKILL.md`](../../skills/frt-1910-counterexample-ir/SKILL.md)
- **FRT-1911 — CEGAR Loop** — [`skills/frt-1911-cegar-loop/SKILL.md`](../../skills/frt-1911-cegar-loop/SKILL.md)
- **FRT-1912 — CEGIS Loop** — [`skills/frt-1912-cegis-loop/SKILL.md`](../../skills/frt-1912-cegis-loop/SKILL.md)
- **FRT-1913 — Counterexample Guided Repair** — [`skills/frt-1913-counterexample-guided-repair/SKILL.md`](../../skills/frt-1913-counterexample-guided-repair/SKILL.md)
- **FRT-1914 — Proof Carrying Pack** — [`skills/frt-1914-proof-carrying-pack/SKILL.md`](../../skills/frt-1914-proof-carrying-pack/SKILL.md)
- **FRT-1915 — Hidden Golden Mutation and Adversarial Bank** — [`skills/frt-1915-hidden-golden-mutation-and-adversarial-bank/SKILL.md`](../../skills/frt-1915-hidden-golden-mutation-and-adversarial-bank/SKILL.md)
- **FRT-1916 — Semantic Drift Detector** — [`skills/frt-1916-semantic-drift-detector/SKILL.md`](../../skills/frt-1916-semantic-drift-detector/SKILL.md)
- **FRT-1917 — Proof Evidence Graph** — [`skills/frt-1917-proof-evidence-graph/SKILL.md`](../../skills/frt-1917-proof-evidence-graph/SKILL.md)
- **FRT-1918 — Formal Assurance Certification** — [`skills/frt-1918-formal-assurance-certification/SKILL.md`](../../skills/frt-1918-formal-assurance-certification/SKILL.md)

## 7. Orchestration Workflow

1. Validate prerequisite batch certificates, versions, digests and compatibility contracts.
2. Resolve the exact project, tenant, workspace, source snapshot, target profile, packs, policy and environment.
3. Compile batch-specific typed contracts and obligations before changing code or state.
4. Execute deterministic and independently verifiable steps first.
5. Use restricted agent proposals only for bounded unresolved work; never permit direct certification.
6. Run positive, negative, adversarial, mutation and recovery verification appropriate to risk.
7. Store all artifacts and findings in the evidence graph with immutable digests.
8. Stop on any R4/R5 blocker and create an actionable escalation packet.
9. Issue the G19 certificate only when every mandatory gate passes.

## 8. Common Implementation Surfaces

```text
packages/contracts/g19/
packages/runtime/g19/
services/control-plane/g19/
services/workers/g19/
apps/web-console/src/features/g19/
apps/admin-console/src/features/g19/
tests/g19/
evidence/g19/
```

## 9. Batch API

```text
POST /v1/generation-batches/g19/runs
GET  /v1/generation-batches/g19/runs/{run_id}
POST /v1/generation-batches/g19/runs/{run_id}/plan
POST /v1/generation-batches/g19/runs/{run_id}/start
POST /v1/generation-batches/g19/runs/{run_id}/pause
POST /v1/generation-batches/g19/runs/{run_id}/resume
POST /v1/generation-batches/g19/runs/{run_id}/cancel
GET  /v1/generation-batches/g19/runs/{run_id}/evidence
POST /v1/generation-batches/g19/runs/{run_id}/certify
```

## 10. CLI

```bash
frt batch g19 plan --project <project> --release <release>
frt batch g19 run --plan <plan>
frt batch g19 verify --run <run-id>
frt batch g19 certify --run <run-id> --level FA5
```

## 11. Verification

- Schema validation and compatibility tests.
- Unit and component tests for deterministic logic.
- API, event, data and permission contract tests.
- End-to-end positive, failure, cancellation, retry and recovery journeys.
- Mutation and adversarial tests for critical invariants.
- Evidence digest, lineage, certificate invalidation and reproducibility tests.

## 12. Release Gates

- [ ] R5证明不得由LLM自证
- [ ] Kernel验证失败不得降级为通过
- [ ] Assumption和Scope完整披露
- [ ] Counterexample必须可重放
- [ ] Proof对应精确Digest
- [ ] 未形式化部分由差分和运行测试覆盖

## 13. Stop and Escalate When

- A prerequisite certificate is missing, stale, revoked or out of scope.
- A critical semantic, authority, permission, data, security or recovery decision is unknown.
- The only apparent implementation requires weakening tests, policy, isolation, audit or evidence.
- The environment cannot provide the real compiler, runtime, device, provider or independent oracle required for certification.
- The requested change exceeds the approved batch or release scope.

## 14. Definition of Done

- Every listed Skill has an installable `SKILL.md` and unique ID.
- All required contracts and schemas are versioned and validated.
- Runtime, API, CLI and UI paths are implemented or explicitly marked not applicable with approved evidence.
- Positive, negative, failure, mutation and recovery tests pass.
- Findings have owners and no unresolved critical blockers remain.
- Evidence is immutable, reproducible and bound to exact digests.
- A valid `FA5` or policy-approved lower certificate is issued for the exact scope.
