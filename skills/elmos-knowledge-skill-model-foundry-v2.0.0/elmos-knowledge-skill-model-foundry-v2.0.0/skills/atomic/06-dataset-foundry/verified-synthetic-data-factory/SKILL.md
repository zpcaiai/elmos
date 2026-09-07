---
name: verified-synthetic-data-factory
description: Use this skill when Elmos must perform verified synthetic data factory as part of the 06-dataset-foundry production workflow, with typed contracts, policy enforcement, evidence capture, and rollback.
license: Proprietary-Elmos-Commercial
compatibility: Elmos v3 harness; K6 Dataset Foundry; policy and evidence services required.
metadata:
  version: "2.0.0"
  pack: 06-dataset-foundry
  priority: P1
  exposure: atomic-registry-only
allowed-tools: dataset.build lineage.emit pii.redact license.check eval.freeze
---

# verified-synthetic-data-factory

## 能力目标

仅保留通过解析、执行、差分、变异或证明验证的合成数据。

## 何时使用

当任务事实与本能力目标一致，并且注册表确认租户权限、版本兼容、依赖、风险和运行环境满足条件时使用。不要仅因关键词相似而触发。

## 输入契约

- 任务契约、租户/项目/仓库身份与风险等级；
- 与本能力相关的知识快照、Semantic IR、环境或数据版本；
- 明确的验收标准、预算、机器 Wall-clock 截止时间和副作用边界。

## 执行流程

1. 验证前置条件、权限、数据用途、版本和依赖。
2. 建立只读基线、内容哈希、检查点和回滚目标。
3. 生成最小执行计划，优先使用确定性工具和可重放脚本。
4. 执行能力动作，记录每个 Tool Call、模型、参数、环境和产物。
5. 运行独立验证器；失败时只允许受控修复，不得删除或弱化验收门。
6. 聚合 Evidence Contract，明确通过项、失败项、不确定项和人工升级条件。

## 输出与证据

- 结构化结果与内容地址；
- 输入、输出、依赖、模型、Skill、知识和工具版本；
- 必须门：rights-cleared, tenant-safe, deduplicated, split-safe, quality-threshold；
- 机器 Wall-clock、Token、GPU、工具与存储成本；
- 回滚/补偿记录和未决风险。

## 禁止行为

- 未授权跨租户读取、训练或复用；
- 以模型自评替代编译、测试、差分、证明或策略检查；
- 为通过测试而删除测试、硬编码答案、扩大权限或隐藏错误；
- 覆盖不可变发布物、跳过签名、伪造来源或证据。

## 失败与回滚

任何硬门失败时输出 `blocked`，保留工作区与证据，恢复到检查点；高风险或无法确定的情况升级人工，不得声称生产可用。
