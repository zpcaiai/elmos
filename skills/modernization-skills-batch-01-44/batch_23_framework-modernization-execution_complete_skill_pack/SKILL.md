---
name: batch-23-framework-modernization-execution
description: "Implement the complete Batch 23 skill system for Framework Modernization Execution Packs."
version: 1.0.0
status: implementation-ready
---

# Batch 23: Framework Modernization Execution Packs

## Mission

把 Framework Contract 和方向性 Recipe 落到真实应用启动、路由、DI、安全、ORM、消息、配置和测试闭环，形成精确版本的 Framework Execution Pack。

## Upstream Contract

本 Batch 必须消费 Batch 22 的正式输出，并继承 Batch 01–05 的 Directional Route、CSIR、Transformation、Codegen、Evidence、Unknown Preservation 与 Conservative Certification 约束。任何契约冲突必须停止并生成 Compatibility Finding，不得复制平行模型。

## Capability Coverage

- Runtime Fingerprint
- Framework Contract
- Exact Version Tuple
- App Bootstrap
- Route/Binding
- DI Scope
- Security
- ORM/Transaction
- Messaging/Cache/Scheduler
- Config/Observability
- Framework Tests
- Coexistence/Strangler

## Skill Inventory

1. `$b23-framework-modernization-execution-orchestrator`
2. `$b23-framework-modernization-execution-domain-model`
3. `$b23-framework-modernization-execution-discovery-inventory`
4. `$b23-framework-modernization-execution-capability-planning`
5. `$b23-framework-modernization-execution-deterministic-engine`
6. `$b23-framework-modernization-execution-adapter-provider`
7. `$b23-framework-modernization-execution-workflow-runtime`
8. `$b23-framework-modernization-execution-lineage-reconciliation`
9. `$b23-framework-modernization-execution-security-policy`
10. `$b23-framework-modernization-execution-human-approval`
11. `$b23-framework-modernization-execution-observability-economics`
12. `$b23-framework-modernization-execution-corpus-benchmark`
13. `$b23-framework-modernization-execution-failure-recovery`
14. `$b23-framework-modernization-execution-integration-api`
15. `$b23-framework-modernization-execution-lifecycle-recertification`
16. `$b23-framework-modernization-execution-certification-gate`

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
