---
name: batch-06-standard-library-dependency-compatibility
description: "Implement the complete Batch 06 skill system for Standard Library, Dependency Mapping and Compatibility Runtime."
version: 1.0.0
status: implementation-ready
---

# Batch 06: Standard Library, Dependency Mapping and Compatibility Runtime

## Mission

建立跨 Java、.NET、Python、Node.js、C++、Go、Rust 与前端生态的标准库和第三方依赖映射，生成锁定依赖、兼容层、Wrapper、Sidecar 与保留原服务决策。

## Upstream Contract

本 Batch 必须消费 Batch 05 的正式输出，并继承 Batch 01–05 的 Directional Route、CSIR、Transformation、Codegen、Evidence、Unknown Preservation 与 Conservative Certification 约束。任何契约冲突必须停止并生成 Compatibility Finding，不得复制平行模型。

## Capability Coverage

- Java SDK 与 .NET BCL 映射
- Python 标准库与 Java/.NET/Node 对应
- Maven/NuGet/PyPI/npm/Cargo/Go Modules 依赖映射
- 版本与运行时兼容矩阵
- 许可证、CVE 与供应链策略
- 依赖替代注册表
- Compatibility Shim 与 Wrapper
- Sidecar 与保留原服务
- Lockfile 与 SBOM
- 弃用与退出治理

## Skill Inventory

1. `$b06-standard-library-dependency-compatibility-orchestrator`
2. `$b06-standard-library-dependency-compatibility-domain-model`
3. `$b06-standard-library-dependency-compatibility-discovery-inventory`
4. `$b06-standard-library-dependency-compatibility-capability-planning`
5. `$b06-standard-library-dependency-compatibility-deterministic-engine`
6. `$b06-standard-library-dependency-compatibility-adapter-provider`
7. `$b06-standard-library-dependency-compatibility-workflow-runtime`
8. `$b06-standard-library-dependency-compatibility-lineage-reconciliation`
9. `$b06-standard-library-dependency-compatibility-security-policy`
10. `$b06-standard-library-dependency-compatibility-human-approval`
11. `$b06-standard-library-dependency-compatibility-observability-economics`
12. `$b06-standard-library-dependency-compatibility-corpus-benchmark`
13. `$b06-standard-library-dependency-compatibility-failure-recovery`
14. `$b06-standard-library-dependency-compatibility-integration-api`
15. `$b06-standard-library-dependency-compatibility-lifecycle-recertification`
16. `$b06-standard-library-dependency-compatibility-certification-gate`

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
