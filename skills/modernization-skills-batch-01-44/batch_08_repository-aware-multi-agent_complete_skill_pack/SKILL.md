---
name: batch-08-repository-aware-multi-agent
description: "Implement the complete Batch 08 skill system for Repository-Aware Multi-Agent, Context and RAG System."
version: 1.0.0
status: implementation-ready
---

# Batch 08: Repository-Aware Multi-Agent, Context and RAG System

## Mission

建立受证据约束的仓库级 Agent 系统，统一 Context、RAG、模型路由、工具权限、成本预算和人工升级，并确保 Agent 不能成为产品可信根。

## Upstream Contract

本 Batch 必须消费 Batch 07 的正式输出，并继承 Batch 01–05 的 Directional Route、CSIR、Transformation、Codegen、Evidence、Unknown Preservation 与 Conservative Certification 约束。任何契约冲突必须停止并生成 Compatibility Finding，不得复制平行模型。

## Capability Coverage

- Repository Context Graph
- 语义检索与 RAG
- Context Window Planner
- Translation/Dependency/Framework/Repair Agents
- Model Router
- Tool Allowlist
- Prompt Injection 防御
- 短期与项目记忆
- Token/Cost Budget
- Agent Patch Envelope
- Human Escalation
- Trace 与独立验证

## Skill Inventory

1. `$b08-repository-aware-multi-agent-orchestrator`
2. `$b08-repository-aware-multi-agent-domain-model`
3. `$b08-repository-aware-multi-agent-discovery-inventory`
4. `$b08-repository-aware-multi-agent-capability-planning`
5. `$b08-repository-aware-multi-agent-deterministic-engine`
6. `$b08-repository-aware-multi-agent-adapter-provider`
7. `$b08-repository-aware-multi-agent-workflow-runtime`
8. `$b08-repository-aware-multi-agent-lineage-reconciliation`
9. `$b08-repository-aware-multi-agent-security-policy`
10. `$b08-repository-aware-multi-agent-human-approval`
11. `$b08-repository-aware-multi-agent-observability-economics`
12. `$b08-repository-aware-multi-agent-corpus-benchmark`
13. `$b08-repository-aware-multi-agent-failure-recovery`
14. `$b08-repository-aware-multi-agent-integration-api`
15. `$b08-repository-aware-multi-agent-lifecycle-recertification`
16. `$b08-repository-aware-multi-agent-certification-gate`

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
