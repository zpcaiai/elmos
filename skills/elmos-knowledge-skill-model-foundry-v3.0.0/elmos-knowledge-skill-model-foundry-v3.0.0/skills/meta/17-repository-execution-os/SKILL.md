---
name: elmos-17-repository-execution-os
description: Use this skill when an Elmos task requires the Repository Execution OS / 仓库级执行操作系统 capability pack. It routes to compatible atomic skills, enforces policy and evidence gates, and builds a durable production workflow.
license: Proprietary-Elmos-Commercial
compatibility: Elmos Proof-Driven Agentic Harness v3+; registry, policy, evidence, workspace and verification services required.
metadata:
  version: "3.0.0"
  pack: 17-repository-execution-os
  business-line: repository-execution
  exposure: meta
allowed-tools: skill.registry.read policy.evaluate evidence.write workflow.plan
---

# Repository Execution OS / 仓库级执行操作系统

## 目标

把超大仓库准入、环境复现、并行 Agent、工作区所有权、补丁合并、长任务恢复和交付证据收敛为可靠执行底座。

## 路由与编排规则

1. 读取任务契约、租户权限、仓库/数据/模型身份、目标版本、风险和商业验收。
2. 查询原子 Skill Registry，过滤不兼容、未签名、已撤销、跨租户或证据不足能力。
3. 先选择确定性分析与最小风险 Skill，再组合生成、转换、验证、发布和回滚 DAG。
4. 高风险动作必须绑定环境所有权权限、检查点、人工审批、独立验证和补偿事务。
5. 输出 Skill 选择理由、依赖、未选理由、机器 Wall-clock ETA、成本、证据和残余风险。

## 生命周期覆盖

`discover → characterize → model → plan → transform/generate → verify → release/cutover → operate → learn`

## 原子能力

本包包含 **34** 个原子 Skill。启动时只暴露 Meta-Skill；默认最多返回 16 个候选、激活 8 个，超过时按阶段拆分执行。

## 硬门

repository-baseline-valid, workspace-isolated, change-set-mergeable, recovery-tested, delivery-provenance-complete。

## 状态说明

本包提供商业生产级能力规范与实现契约，不虚假代表所有 Runtime Adapter 已编码完成。每个原子 Skill 仍须达到声明的 E0-E5 认证目标后方可进入生产。
