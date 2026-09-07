---
name: batch-07-framework-contract-recipe-packs
description: "Implement the complete Batch 07 skill system for Framework Contract Model and Framework Migration Recipe Packs."
version: 1.0.0
status: implementation-ready
---

# Batch 07: Framework Contract Model and Framework Migration Recipe Packs

## Mission

把 Spring Boot、ASP.NET Core、FastAPI、Django、Flask、NestJS、Express 等框架的路由、DI、安全、ORM、配置和运行期语义转化为可认证的方向性 Framework Pack。

## Upstream Contract

本 Batch 必须消费 Batch 06 的正式输出，并继承 Batch 01–05 的 Directional Route、CSIR、Transformation、Codegen、Evidence、Unknown Preservation 与 Conservative Certification 约束。任何契约冲突必须停止并生成 Compatibility Finding，不得复制平行模型。

## Capability Coverage

- Framework Contract Model
- 精确源目标版本指纹
- REST/RPC 路由与绑定
- DTO、Validation 与 Serialization
- DI 容器与 Scope
- Authentication/Authorization
- ORM、事务与迁移
- 配置与 Secret 引用
- Logging/Tracing/Metrics
- Cache、Messaging、Scheduler
- OpenAPI 与测试契约
- Coexistence/Strangler/Adapter

## Skill Inventory

1. `$b07-framework-contract-recipe-packs-orchestrator`
2. `$b07-framework-contract-recipe-packs-domain-model`
3. `$b07-framework-contract-recipe-packs-discovery-inventory`
4. `$b07-framework-contract-recipe-packs-capability-planning`
5. `$b07-framework-contract-recipe-packs-deterministic-engine`
6. `$b07-framework-contract-recipe-packs-adapter-provider`
7. `$b07-framework-contract-recipe-packs-workflow-runtime`
8. `$b07-framework-contract-recipe-packs-lineage-reconciliation`
9. `$b07-framework-contract-recipe-packs-security-policy`
10. `$b07-framework-contract-recipe-packs-human-approval`
11. `$b07-framework-contract-recipe-packs-observability-economics`
12. `$b07-framework-contract-recipe-packs-corpus-benchmark`
13. `$b07-framework-contract-recipe-packs-failure-recovery`
14. `$b07-framework-contract-recipe-packs-integration-api`
15. `$b07-framework-contract-recipe-packs-lifecycle-recertification`
16. `$b07-framework-contract-recipe-packs-certification-gate`

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
