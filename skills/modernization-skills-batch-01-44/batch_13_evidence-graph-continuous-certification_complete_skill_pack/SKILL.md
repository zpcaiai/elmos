---
name: batch-13-evidence-graph-continuous-certification
description: "Implement the complete Batch 13 skill system for Evidence Graph, Independent Oracle and Continuous Certification."
version: 1.0.0
status: implementation-ready
---

# Batch 13: Evidence Graph, Independent Oracle and Continuous Certification

## Mission

建立内容寻址、不可变、可签名的 Evidence Graph，隔离 Builder 与 Verifier，管理独立 Oracle、证书颁发、过期、降级、暂停、撤销和持续重新认证。

## Upstream Contract

本 Batch 必须消费 Batch 12 的正式输出，并继承 Batch 01–05 的 Directional Route、CSIR、Transformation、Codegen、Evidence、Unknown Preservation 与 Conservative Certification 约束。任何契约冲突必须停止并生成 Compatibility Finding，不得复制平行模型。

## Capability Coverage

- Artifact/Execution/Observation/Finding/Certificate IR
- Content-addressed Store
- Evidence Lineage Graph
- Builder/Verifier Isolation
- Independent Oracle Registry
- Certificate Authority
- Trust Levels
- Expiry/Downgrade/Suspension/Revocation
- Transparency Log
- Red-team Evidence
- Evidence Export/Offline Verify
- EA1–EA5

## Skill Inventory

1. `$b13-evidence-graph-continuous-certification-orchestrator`
2. `$b13-evidence-graph-continuous-certification-domain-model`
3. `$b13-evidence-graph-continuous-certification-discovery-inventory`
4. `$b13-evidence-graph-continuous-certification-capability-planning`
5. `$b13-evidence-graph-continuous-certification-deterministic-engine`
6. `$b13-evidence-graph-continuous-certification-adapter-provider`
7. `$b13-evidence-graph-continuous-certification-workflow-runtime`
8. `$b13-evidence-graph-continuous-certification-lineage-reconciliation`
9. `$b13-evidence-graph-continuous-certification-security-policy`
10. `$b13-evidence-graph-continuous-certification-human-approval`
11. `$b13-evidence-graph-continuous-certification-observability-economics`
12. `$b13-evidence-graph-continuous-certification-corpus-benchmark`
13. `$b13-evidence-graph-continuous-certification-failure-recovery`
14. `$b13-evidence-graph-continuous-certification-integration-api`
15. `$b13-evidence-graph-continuous-certification-lifecycle-recertification`
16. `$b13-evidence-graph-continuous-certification-certification-gate`

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
