---
name: elmos-12-observability-lineage-finops
description: Use this skill when an Elmos task requires the 12-observability-lineage-finops capability pack, including planning, selecting atomic skills, enforcing evidence gates, and producing production-grade artifacts.
license: Proprietary-Elmos-Commercial
compatibility: Elmos v3 harness; registry access; policy engine; evidence store.
metadata:
  version: "2.0.0"
  pack: 12-observability-lineage-finops
  exposure: meta
allowed-tools: skill.registry.read policy.evaluate evidence.write
---

# 12-observability-lineage-finops

## 目标

统一追踪知识、检索、Skill、模型、工具、训练、证据、成本和业务价值，并支持重放和根因分析。

## 使用方式

1. 先读取任务契约、租户策略、仓库事实和风险等级。
2. 查询 `registry/skill-catalog.yaml`，只选择与任务、版本和权限相容的原子 Skill。
3. P0/P1 高风险任务必须声明 Evidence Contract、回滚策略和人工审批条件。
4. 原子 Skill 执行后聚合证据；任何硬门失败都不得宣称完成或进入生产。

## 原子能力

本包包含 28 个原子 Skill。默认最多返回 12 个候选、激活 6 个；超出时必须分阶段编排。

## 必须输出

- 选中的 Skill 与版本、选择理由和未选理由；
- 依赖、权限、环境和知识快照；
- 执行 DAG、检查点、成本与机器 Wall-clock ETA；
- 测试、差分、证明、安全、风险和回滚证据；
- 未决问题与人工升级条件。
