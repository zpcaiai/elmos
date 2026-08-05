---
name: b40-adversarial-security-privacy-deterministic-engine
description: "实现可重放、稳定排序、内容寻址、幂等和有界执行的确定性核心。 Scope: Adversarial Security, Privacy and Supply-Chain Assurance."
version: 1.0.0
batch: batch-40
risk: critical
status: implementation-ready
---

# Deterministic Engine

## Objective

实现可重放、稳定排序、内容寻址、幂等和有界执行的确定性核心。

本 Skill 属于 **Batch 40: Adversarial Security, Privacy and Supply-Chain Assurance**。Batch 总目标：对迁移控制面、Runner、Skill、模型、数据、供应链和管理端实施威胁建模、攻击面、身份权限、Prompt Injection、漏洞、隐私和持续安全认证。

## Scope

- Threat Model
- Attack Surface
- Authentication
- Authorization/Tenant Isolation
- Session/Token
- API/Input/File
- Secrets/Keys
- Supply Chain/SBOM/Vulnerability
- Malicious Skill/Prompt Injection
- SAST/DAST/Fuzz/Pentest
- Rate Abuse
- Privacy/Consent/Retention/Deletion
- Secure Admin
- Incident Response
- Security Recertification

## Inputs

- 上游已认证 CapabilityPackage、Snapshot、EvidenceRef 与 PolicyRef。
- 精确版本、Tenant、Project、Scope、Owner 和 Idempotency Key。
- 本 Batch 相关资产、约束、预算、审批与运行环境。

## Outputs

- `DeterministicResult`
- `ExecutionJournal`
- `OutputDigest`
- `EvidenceRefs`
- `KnownLimitations`
- `CompletionReport`

## Workflow

1. 锁定工具、规则、输入、环境和随机性。
2. 规范化查询、排序、分区与执行计划。
3. 在内容寻址 Workspace 中执行并记录 Journal。
4. 验证相同输入在不同并发度下输出 Digest 一致。
5. 暴露无法确定的区域，不用猜测填补。

## Invariants and Hard Rules

- 不得把计划、模型自评、静态校验或文档状态冒充真实执行成功。
- 不得静默删除 Unknown、Unsupported、Opaque、Inconclusive 或既有失败。
- 不得允许 Agent、插件或外部 Provider 修改测试、Golden、证书、验证策略或权限策略。
- 所有高影响结论必须绑定 Snapshot、版本、Digest、Evidence 和适用范围。
- 不可逆操作必须经过明确审批，并具有已演练的回退、补偿或人工恢复路径。

## Required Tests

- 对 Threat Model 的正常路径产生可重放证据。
- 缺少 Attack Surface 证据时必须降级或阻断。
- 相同输入以 1/4/16 Worker 执行时确定性输出一致（适用时）。
- 跨租户、越权、伪造证书和删除失败测试均被拒绝。
- 上游 Snapshot 或 Major Schema 变化后旧结果失效。

## Verification

- Schema 与版本兼容验证。
- 权限、租户隔离、Secret、路径和不受信输入负例。
- 失败、超时、取消、重试、回滚和重复事件测试。
- Evidence Digest、Producer、时间、范围和独立性校验。
- 保守 Gate：仅修改状态字段不得获得更高认证。

## Stop and Escalate

- 输入证书缺失、过期、撤销或与当前 Snapshot 不一致。
- 出现无法约束的副作用、未知权限、不可逆数据风险或跨租户访问。
- Provider 能力、版本或许可无法确认。
- Blocking Verification 失败、证据矛盾或结果不可重现。

## Definition of Done

- 所有声明输入和输出均有版本化 Schema 与 Digest。
- Workflow 可暂停、恢复、取消，副作用幂等且可对账。
- P0 测试全部通过；Critical P1 通过或有到期、可追踪的批准豁免。
- 未知、限制、人工任务和未完成能力被明确披露。
- 生成的状态不超过实际执行和证据能够证明的等级。

## Completion Report

完成后报告：修改文件、Schema/Migration、运行命令、测试结果、指标分母、证据位置、批准、失败与回滚、未解决风险、下一 Batch 接口。
