---
id: 39-output-versioning-retention
name: Output Versioning, Retention & Lifecycle
version: 1.1.0
category: governance
depends_on:
  - 30-checkpoint-resume-idempotency
  - 35-governance-approval-audit
  - 38-project-output-bundle-publishing
---

# Output Versioning, Retention & Lifecycle

## 目标

管理项目产出和测试文件的修订、过期、替代、保留、恢复、Legal Hold、内容去重与安全垃圾回收。

## 输入契约

- 当前和历史 ProjectOutput/Artifact/Bundle/Lineage
- 需求、代码、Adapter、测试策略和门禁版本差异
- 保留、合规、成本和租户策略

## 输出契约

- revision diff、stale/superseded 标记和新旧映射
- 保留期限、legal hold、恢复点和 GC 候选
- 内容寻址引用计数、删除审计与成本统计
- 最新可用、最新认证和指定历史版本查询

## 执行步骤

1. 比较输入快照、需求、代码符号、测试策略和工具版本。
2. 精确标记受影响测试文件为 stale，并触发重新生成/验证。
3. 新 revision 发布后，将旧产出标记 superseded，但保持可下载和可审计。
4. 根据认证、安全事件和合规状态选择保留等级。
5. 对 Blob 进行内容寻址去重和引用计数。
6. 两阶段垃圾回收：候选 → 延迟窗口 → 再校验引用 → 删除。
7. 支持恢复历史测试文件、重放历史 Run 和比较测试变化。

## 不可违反的控制

- Required 测试文件 stale 时不得认证。
- 仍被 Manifest、证书、缺陷、安全事件或 legal hold 引用的对象不得删除。
- 删除必须有权限、审计、可恢复窗口和幂等键。
- 不得静默覆盖或丢失历史修复前后的测试证据。

## 完成判定

- 用户可查询最新、认证和历史项目产出。
- 测试文件变化可解释到需求/代码/策略变化。
- GC 不会删除仍被引用的文件，保留成本可统计。
