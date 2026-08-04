---
name: batch-19-seventy-two-directional-route-packs
description: "Implement the complete Batch 19 skill system for 72 Directional Executable Generator Packs."
version: 1.0.0
status: implementation-ready
---

# Batch 19: 72 Directional Executable Generator Packs

## Mission

为 Java、C#、Python、JavaScript、TypeScript、C++、Go、Rust 与 Dart 九种主要语言家族建立 72 条有向转换路线；Vue、React、Flutter 作为框架后端组合进入路线包，逐条实现 Frontend、Lowering、Backend、依赖映射、完整项目生成、Corpus、Benchmark 和认证。

## Upstream Contract

本 Batch 必须消费 Batch 18 的正式输出，并继承 Batch 01–05 的 Directional Route、CSIR、Transformation、Codegen、Evidence、Unknown Preservation 与 Conservative Certification 约束。任何契约冲突必须停止并生成 Compatibility Finding，不得复制平行模型。

## Capability Coverage

- 9 Core Source Frontends
- 9 Core Target Backends
- 72 Directed Route Manifests
- Vue/React/Flutter Framework Combinations
- Path-specific Lowering
- Dependency Mapping
- Complete Project Generation
- Golden Corpus
- Hidden/Holdout Corpus
- Adversarial Corpus
- Correctness/Performance Benchmark
- GP1–GP5

## Skill Inventory

1. `$b19-seventy-two-directional-route-packs-orchestrator`
2. `$b19-seventy-two-directional-route-packs-domain-model`
3. `$b19-seventy-two-directional-route-packs-discovery-inventory`
4. `$b19-seventy-two-directional-route-packs-capability-planning`
5. `$b19-seventy-two-directional-route-packs-deterministic-engine`
6. `$b19-seventy-two-directional-route-packs-adapter-provider`
7. `$b19-seventy-two-directional-route-packs-workflow-runtime`
8. `$b19-seventy-two-directional-route-packs-lineage-reconciliation`
9. `$b19-seventy-two-directional-route-packs-security-policy`
10. `$b19-seventy-two-directional-route-packs-human-approval`
11. `$b19-seventy-two-directional-route-packs-observability-economics`
12. `$b19-seventy-two-directional-route-packs-corpus-benchmark`
13. `$b19-seventy-two-directional-route-packs-failure-recovery`
14. `$b19-seventy-two-directional-route-packs-integration-api`
15. `$b19-seventy-two-directional-route-packs-lifecycle-recertification`
16. `$b19-seventy-two-directional-route-packs-certification-gate`

## Shared Architecture

```text
Versioned Input + Certificate
→ Discovery / Planning
→ Deterministic Core + Approved Adapters
→ Durable Workflow / Isolated Runner
→ Reconciliation / Independent Verification
→ Evidence Graph
→ Human Gate where required
→ Conservative Certificate
```

## Shared Contracts

- `CapabilityPackage`
- `EvidenceRef`
- `WorkflowRun`
- `ApprovalDecision`
- `MetricSnapshot`
- `CertificationDecision`
- `LifecycleRecord`

## Global Invariants

- Evidence before claim; execution before success state.
- Unknown、Unsupported、Opaque 和 Inconclusive 不得被静默抹除。
- Agent 只能提出 Patch/Decision Proposal，不能自批、自证或直接发布。
- 所有 Provider/Tool/Model/Rule 必须锁定版本和权限。
- 所有不可逆动作必须有批准、预演、回退和副作用收据。
- 任何认证都绑定精确 Scope、Snapshot、Digest、版本、Policy 和有效期。

## Certification Gate

Batch Gate 至少检查：Schema、输入证书、真实执行、P0 测试、Critical P1、Holdout/Representative Corpus、Security Negative Tests、Rollback/Recovery、Evidence Completeness、Human Approval、Unknown/Exception Register 和 Certificate Invalidation。

## Definition of Done

全部子 Skill 结构完整并通过静态校验；真正的 `certified` 状态只能在目标仓库、工具链、Provider 和运行环境执行其 Required Tests 后获得。此技能包自身的静态 PASS 不代表产品实现已完成。
