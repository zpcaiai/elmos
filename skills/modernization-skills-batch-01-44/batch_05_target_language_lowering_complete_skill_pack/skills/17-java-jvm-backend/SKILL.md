---
name: b05-java-jvm-backend
description: "Implement the deterministic-engine responsibility for Batch 05. Scope: Batch 5：Target Language Lowering、Framework Backend 与 Idiomatic Code Generation."
version: 1.0.0
batch: batch-05
archetype: deterministic-engine
risk: medium
status: implementation-ready
---

# Java Jvm Backend

## Objective

Implement the deterministic-engine responsibility for Batch 05.

本 Skill 属于 **Batch 05: Batch 5：Target Language Lowering、Framework Backend 与 Idiomatic Code Generation**,承担运行时原型 `deterministic-engine` 的职责,并由
`scripts/modernization_b01_44` 中的同名执行路径实际驱动。

## Scope

- 运行时原型:`deterministic-engine`
- 上游契约:Batch 04 认证输出(Batch 01 为 `genesis`)
- 下游消费者:Batch 06

## Inputs

- 已认证的上游 CapabilityPackage、Snapshot、EvidenceRef 与 PolicyRef。
- 精确版本、Tenant、Project、Scope、Owner 与 Idempotency Key。
- 本 Batch 相关资产、约束、预算与审批记录。

## Outputs

- `DeterministicResult`
- `EvidenceRefs`
- `CompletionReport`
- `EvidenceRefs`
- `KnownLimitations`
- `CompletionReport`

## Workflow

1. 在信任边界校验输入,拒绝未建模字段。
2. 校验租户归属与默认拒绝能力,记录审计。
3. 校验上游证书存在、未过期且状态不低于最低要求。
4. 以稳定排序、内容寻址的方式执行本原型的确定性工作。
5. 产出证据并写入血缘图,保留 Unknown。
6. 由保守 Gate 依据实际存在的证据派生状态,而非采用请求声明的状态。

## Invariants and Hard Rules

- 不得把计划、模型自评、静态校验或文档状态冒充真实执行成功。
- 不得静默删除 Unknown、Unsupported、Opaque、Inconclusive 或既有失败。
- 不得允许 Agent、插件或外部 Provider 修改测试、Golden、证书、验证策略或权限策略。
- 所有高影响结论必须绑定 Snapshot、版本、Digest、Evidence 和适用范围。
- 不可逆操作必须经过明确审批,并具有已演练的回退、补偿或人工恢复路径。

## Required Tests

- 正常路径产生可重放证据,且输出 Digest 与 Worker 数无关。
- 缺少上游证书时执行被阻断。
- 跨租户、越权、伪造证书和删除失败测试均被拒绝。
- 重复事件只产生一次副作用;Runner 断开后 Lease 过期进入 reconciling。
- Evidence 过期后证书转为 stale 并触发重认证。

## Verification

- Schema 与版本兼容验证(`schemas/` 下的 Draft 2020-12 契约)。
- 权限、租户隔离、Secret、路径和不受信输入负例。
- 失败、超时、取消、重试、回滚和重复事件测试。
- Evidence Digest、Producer、时间、范围和独立性校验。
- 保守 Gate:仅修改状态字段不得获得更高认证。

## Stop and Escalate

- 上游契约冲突、证据缺失或过期。
- 需要不可逆操作但缺少有效审批。
- 确定性校验失败(不同并发度输出不一致)。

## Definition of Done

- 本原型在 `scripts/modernization_b01_44` 中有可执行实现。
- `tests/modernization-b01-44` 中对应用例全部通过。
- 产出的证据、证书与限制项均可被下游 Batch 消费。

## Completion Report

- 执行的 Skill 名称、版本与 Batch。
- 输入 Digest、输出 Digest、Journal Digest。
- 产生的 EvidenceRef 列表与 Gate 判定理由。
- 明确记录的 KnownLimitations 与 Unknown。
