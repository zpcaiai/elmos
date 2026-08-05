---
name: frt-0302-symbol-scope-and-reference-graph
description: Symbol Scope and Reference Graph. G03 Typed Semantic IR与Universal Semantic Type System中的实现级Codex Skill。
version: 1.0.0
skill_id: FRT-0302
batch: G03
risk: critical-by-default
requires_certificate: G02
produces_certificate_family: IR
---

# FRT-0302 — Symbol Scope and Reference Graph

## Objective

在G03范围内实现 **Symbol Scope and Reference Graph**，并确保其结果可以被后续Batch、测试、管理端和证书系统稳定消费。该Skill服务于：建立跨Vue/React/小程序/ArkUI/Flutter的类型和语义中间层; 保留Null、Identity、Effect、Lifecycle、Navigation、Data Authority和UI语义; 每个IR节点绑定Source Range和稳定Semantic ID。

## When to Use

- 实现或修改与 **Symbol Scope and Reference Graph** 对应的Contract、Runtime、API、UI、测试或证据链时。
- 相关代码、Schema、Pack、Policy、环境或依赖变化导致既有Evidence失效时。
- G03 Orchestrator生成该Skill的执行义务时。

## Inputs

- `BatchExecutionContext`：project、tenant、workspace、release、environment、policy与risk。
- `PrerequisiteCertificateSet`：前置Batch有效证书及其Scope/Digest。
- `SourceArtifactSet`：G2 Repository Model与各源AST/模板/元数据。
- `SkillPolicy`：权限、网络、Sandbox、Toolchain、Evidence和停止规则。

## Outputs

- `FRT-0302Result`：版本化、带状态和诊断的结构化结果。
- `FRT-0302EvidenceBundle`：输入、执行、测试、Finding和输出Digest。
- `FRT-0302FindingSet`：error、warning、gap、manual-decision与blocker。
- `FRT-0302CertificateFragment`：供G03批次证书聚合，不得自行宣告全批通过。

## Required Implementation Surfaces

```text
packages/contracts/g03/frt-0302-symbol-scope-and-reference-graph/
packages/runtime/g03/frt-0302-symbol-scope-and-reference-graph/
services/control-plane/g03/frt-0302-symbol-scope-and-reference-graph/
apps/web-console/src/features/g03/frt-0302-symbol-scope-and-reference-graph/
apps/admin-console/src/features/g03/frt-0302-symbol-scope-and-reference-graph/
tests/g03/frt-0302-symbol-scope-and-reference-graph/
```

每个Surface不存在时，必须在Manifest中以`not_applicable`说明原因和批准Evidence，不得静默省略。

## Workflow

1. Resolve the exact input versions, source snapshot, target profile, pack lock, policy and environment.
2. Validate prerequisite certificates and reject stale, revoked or scope-mismatched evidence.
3. Load the typed contracts owned by this Skill; generate missing schemas before runtime code.
4. Discover the smallest compatible extension point in the existing repository; do not create a parallel subsystem.
5. Implement deterministic core logic and stable IDs first.
6. Add authorization, tenant scope, idempotency, audit and evidence hooks at every trust boundary.
7. Implement API, CLI and UI operations required by the parent batch.
8. Generate positive, negative, concurrency, failure, recovery and mutation tests based on risk.
9. Run repository-native format, lint, typecheck, build, unit, integration and E2E suites.
10. Store results in the evidence graph and return a bounded certificate fragment.

## Hard Rules

- Source repository is read-only; generation, build, tests, mutation and repair run in isolated worktrees or sandboxes.
- Models propose candidates only; compilers, type checkers, formal kernels, independent tests and runtime evidence decide acceptance.
- No silent semantic loss, fake success, empty catch, fixed return, disabled assertion or UI-only authorization is permitted.
- All R4/R5 gates are non-compensatory; a critical failure cannot be hidden by aggregate scores.
- Every authoritative output binds input digests, toolchain, policy, environment, execution and evidence lineage.
- Unknown semantics must stop, emit a typed gap, request a product decision or escalate to a human reviewer.
- This Skill may not edit prerequisite certificates, goldens, expected results, security policy or release gates.
- Direct database status edits are forbidden; use typed commands and authoritative state transitions.
- Any unsupported capability, unverified mapping or unknown result must remain explicit.

## API Contract

```text
POST /v1/skills/frt-0302/runs
GET  /v1/skills/frt-0302/runs/{run_id}
POST /v1/skills/frt-0302/runs/{run_id}/verify
GET  /v1/skills/frt-0302/runs/{run_id}/findings
GET  /v1/skills/frt-0302/runs/{run_id}/evidence
```

## Verification

- Contract valid/invalid fixtures and version compatibility.
- Authorization, object scope, tenant isolation and negative permission tests.
- Deterministic replay with controlled clock, random seed and stable data.
- Failure, timeout, cancellation, retry and stale-result tests where applicable.
- Mutation tests that remove the Skill's critical guard, invariant, mapping or evidence hook.
- Evidence digest and source-to-result lineage verification.

## Stop and Escalate When

- Required source, target, runtime, device or provider evidence is unavailable.
- Implementing the request would require silent loss, guessed authority, unsafe fallback or weakened verification.
- A critical conflict exists between product requirements, business invariants, data authority, security policy or platform capability.
- The change affects a different Batch without a versioned compatibility contract.

## Definition of Done

- The Skill has a unique manifest, versioned schemas and stable API/CLI identifiers.
- All required implementation surfaces are complete or explicitly approved as not applicable.
- No unresolved R4/R5 findings remain.
- Tests pass in a clean, controlled environment and critical mutations are killed.
- Evidence is immutable, traceable and reproducible.
- The parent G03 Orchestrator can consume the result and independently decide certification.
