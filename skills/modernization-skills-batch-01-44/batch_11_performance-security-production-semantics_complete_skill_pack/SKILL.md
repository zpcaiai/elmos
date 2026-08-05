---
name: batch-11-performance-security-production-semantics
description: "Implement the complete Batch 11 skill system for Performance, Security and Production Semantics Validation."
version: 1.0.0
status: implementation-ready
---

# Batch 11: Performance, Security and Production Semantics Validation

## Mission

验证并发、事务、锁、精度、时区、序列化、身份权限、加密、性能、资源生命周期和生产配置语义，阻止只通过功能测试的错误迁移。

## Upstream Contract

本 Batch 必须消费 Batch 10 的正式输出，并继承 Batch 01–05 的 Directional Route、CSIR、Transformation、Codegen、Evidence、Unknown Preservation 与 Conservative Certification 约束。任何契约冲突必须停止并生成 Compatibility Finding，不得复制平行模型。

## Capability Coverage

- Concurrency 与 Scheduling
- Transaction/Isolation/Lock
- Numeric Precision/Overflow
- Time/Timezone/Locale
- Serialization Compatibility
- Authentication
- Authorization/Tenant Isolation
- Cryptography/Secret Handling
- Performance Regression
- Memory/FD/Connection Leak
- Production Configuration
- Capacity 与 SLO

## Skill Inventory

1. `$b11-performance-security-production-semantics-orchestrator`
2. `$b11-performance-security-production-semantics-domain-model`
3. `$b11-performance-security-production-semantics-discovery-inventory`
4. `$b11-performance-security-production-semantics-capability-planning`
5. `$b11-performance-security-production-semantics-deterministic-engine`
6. `$b11-performance-security-production-semantics-adapter-provider`
7. `$b11-performance-security-production-semantics-workflow-runtime`
8. `$b11-performance-security-production-semantics-lineage-reconciliation`
9. `$b11-performance-security-production-semantics-security-policy`
10. `$b11-performance-security-production-semantics-human-approval`
11. `$b11-performance-security-production-semantics-observability-economics`
12. `$b11-performance-security-production-semantics-corpus-benchmark`
13. `$b11-performance-security-production-semantics-failure-recovery`
14. `$b11-performance-security-production-semantics-integration-api`
15. `$b11-performance-security-production-semantics-lifecycle-recertification`
16. `$b11-performance-security-production-semantics-certification-gate`

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
