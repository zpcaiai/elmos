---
name: b43-legacy-coexistence-retirement-certification-gate
description: "只依据不可变证据签发最强可证明状态；缺证据、未知或阻断项必须降级或拒绝。 Scope: Legacy Coexistence, Cutover, Hypercare and Continuous Modernization."
version: 1.0.0
batch: batch-43
risk: critical
status: implementation-ready
---

# Conservative Certification Gate

## Objective

只依据不可变证据签发最强可证明状态；缺证据、未知或阻断项必须降级或拒绝。

本 Skill 属于 **Batch 43: Legacy Coexistence, Cutover, Hypercare and Continuous Modernization**。Batch 总目标：管理 Strangler、旧新路由、共享身份、数据所有权、事件桥、混合版本、切换、Hypercare、回滚、归档、源系统退役和上线后的持续现代化。

## Scope

- Strangler/Facade
- Legacy Routing
- Shared Identity
- Data Ownership
- Event/Protocol Bridge
- Mixed-version Matrix
- Cutover Plan
- Hypercare
- Rollback
- Data Archive
- Decommission
- Source Retirement
- Continuous Modernization
- Incident Learning

## Inputs

- 上游已认证 CapabilityPackage、Snapshot、EvidenceRef 与 PolicyRef。
- 精确版本、Tenant、Project、Scope、Owner 和 Idempotency Key。
- 本 Batch 相关资产、约束、预算、审批与运行环境。

## Outputs

- `SignedCertificate`
- `GateDecision`
- `CertificationEvidencePack`
- `EvidenceRefs`
- `KnownLimitations`
- `CompletionReport`

## Workflow

1. 校验输入 Snapshot、Schema、Policy、Tool 和 Artifact Digest。
2. 检查所有 Blocking 指标、未知、例外、Holdout 和代表性证据。
3. 验证证据来自允许且相互独立的 Producer。
4. 签发 certified、limited、experimental、blocked 或 stale。
5. 生成带限制、有效期、失效条件和签名的 Certificate。

## Invariants and Hard Rules

- 不得把计划、模型自评、静态校验或文档状态冒充真实执行成功。
- 不得静默删除 Unknown、Unsupported、Opaque、Inconclusive 或既有失败。
- 不得允许 Agent、插件或外部 Provider 修改测试、Golden、证书、验证策略或权限策略。
- 所有高影响结论必须绑定 Snapshot、版本、Digest、Evidence 和适用范围。
- 不可逆操作必须经过明确审批，并具有已演练的回退、补偿或人工恢复路径。

## Required Tests

- 对 Strangler/Facade 的正常路径产生可重放证据。
- 缺少 Legacy Routing 证据时必须降级或阻断。
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
