---
name: batch-40-product-entry-modes
description: 统一已有失败项目修复、源项目转换认证和从Skills零开始生成三种入口，并自动选择复用与执行策略。
---

# Batch 40：三种产品入口

## Goal

统一已有失败项目修复、源项目转换认证和从Skills零开始生成三种入口，并自动选择复用与执行策略。

## Position in the system

- Phase: `K 从Skills生成完整项目`
- Included skills: `5`
- Required status vocabulary: `PROVED | VERIFIED | CONDITIONALLY_VERIFIED | REQUIRES_ADAPTER | REQUIRES_HUMAN_REVIEW | UNSUPPORTED | FAILED`

## Batch workflow

1. 选择Repair/Migration/Generation模式
2. 编译Skills与架构蓝图
3. 生成/复用全部构件
4. 构建并执行验收/安全/完整性门禁
5. 输出项目、Runbook和证据

## Shared gates

- 必需Manifest项不得缺失
- 生成代码必须有对应测试或明确豁免
- 未表达的需求不得伪装为已满足

## Dispatch rules

- 当任务涉及 **compare-and-repair** 时，调用 `skills/compare-and-repair/SKILL.md`。
- 当任务涉及 **convert-and-certify** 时，调用 `skills/convert-and-certify/SKILL.md`。
- 当任务涉及 **generate-from-skills** 时，调用 `skills/generate-from-skills/SKILL.md`。
- 当任务涉及 **migration-mode-selector** 时，调用 `skills/migration-mode-selector/SKILL.md`。
- 当任务涉及 **asset-reuse-planner** 时，调用 `skills/asset-reuse-planner/SKILL.md`。

## Skill catalog

| Skill | Responsibility |
|---|---|
| `compare-and-repair` | 输入源仓库与失败目标仓库，检测功能差异、自动修复并重新认证。 |
| `convert-and-certify` | 输入源仓库与目标技术栈，执行评估、转换、验证、修复和证据签发。 |
| `generate-from-skills` | 输入可执行Skills、业务配置、目标栈和部署要求，生成完整可运行项目并验收。 |
| `migration-mode-selector` | 根据源/目标资产、质量、规格和风险选择 Repair、Migration 或 Generation 模式。 |
| `asset-reuse-planner` | 决定源码、测试、Schema、资源、协议、组件和部署资产的复用、适配或重建。 |

## Batch outputs

- `batch-result.yaml`：批次状态、输入、产物和未解决项。
- `evidence-index.json`：所有子 Skill 证据索引。
- `semantic-loss-ledger.json`：不支持、近似、未验证与需人工语义。
- `next-actions.yaml`：下游 Batch、升级、试点或阻断建议。

## Orchestration constraints

- 子 Skill 可并行执行，但存在数据依赖时必须按 `catalog.yaml` 顺序或任务图执行。
- 所有模型输出都只是候选，必须经过本 Batch 对应的客观工具门禁。
- 任一阻断项不得被平均分或整体“高相似度”覆盖。
