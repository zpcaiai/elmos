---
name: batch-12-lossless-semantic-transformation
description: 在能够确定性重写时尽可能保留源结构、注释、格式、位置和未修改代码，支持最小补丁与安全回滚。
---

# Batch 12：Lossless Semantic Transformation

## Goal

在能够确定性重写时尽可能保留源结构、注释、格式、位置和未修改代码，支持最小补丁与安全回滚。

## Position in the system

- Phase: `D 转换定义与规则引擎`
- Included skills: `10`
- Required status vocabulary: `PROVED | VERIFIED | CONDITIONALLY_VERIFIED | REQUIRES_ADAPTER | REQUIRES_HUMAN_REVIEW | UNSUPPORTED | FAILED`

## Batch workflow

1. 验证规则前置条件
2. 优先使用确定性规则
3. 对长尾生成多个候选
4. 按可验证性和成本排序
5. 运行最小构建/静态验证并输出结果集

## Shared gates

- 生成者不是最终裁判
- 不允许静默跳过不支持语义
- 所有修改必须有来源和回滚

## Dispatch rules

- 当任务涉及 **lossless-source-tree** 时，调用 `skills/lossless-source-tree/SKILL.md`。
- 当任务涉及 **type-attributed-tree** 时，调用 `skills/type-attributed-tree/SKILL.md`。
- 当任务涉及 **comment-and-format-preservation** 时，调用 `skills/comment-and-format-preservation/SKILL.md`。
- 当任务涉及 **symbol-safe-renaming** 时，调用 `skills/symbol-safe-renaming/SKILL.md`。
- 当任务涉及 **import-and-namespace-rewriter** 时，调用 `skills/import-and-namespace-rewriter/SKILL.md`。
- 当任务涉及 **minimal-change-generator** 时，调用 `skills/minimal-change-generator/SKILL.md`。
- 当任务涉及 **source-location-mapper** 时，调用 `skills/source-location-mapper/SKILL.md`。
- 当任务涉及 **semantic-diff-generator** 时，调用 `skills/semantic-diff-generator/SKILL.md`。
- 当任务涉及 **transformation-result-set** 时，调用 `skills/transformation-result-set/SKILL.md`。
- 当任务涉及 **rollback-patch-generator** 时，调用 `skills/rollback-patch-generator/SKILL.md`。

## Skill catalog

| Skill | Responsibility |
|---|---|
| `lossless-source-tree` | 构建保留空白、注释、顺序、源位置和语法细节的无损源码树。 |
| `type-attributed-tree` | 为无损源码树附加符号、类型、调用和语义归因。 |
| `comment-and-format-preservation` | 在转换中保留注释、文档、格式和组织约定，避免无关 Diff。 |
| `symbol-safe-renaming` | 在作用域、重载、反射、配置和序列化约束下安全重命名符号。 |
| `import-and-namespace-rewriter` | 精确更新 Import、Namespace、模块路径、别名和依赖声明。 |
| `minimal-change-generator` | 优先生成最小语义变更集，限制无关格式化、重排和风格漂移。 |
| `source-location-mapper` | 维护源 AST、IR、目标代码、诊断和证据之间的双向位置映射。 |
| `semantic-diff-generator` | 生成类型、调用、Effect、状态和观察维度的语义 Diff，而非仅文本 Diff。 |
| `transformation-result-set` | 以统一结果集表达修改、跳过、警告、需人工、失败和证据。 |
| `rollback-patch-generator` | 生成可验证、可逆、按模块或规则粒度回滚的补丁。 |

## Batch outputs

- `batch-result.yaml`：批次状态、输入、产物和未解决项。
- `evidence-index.json`：所有子 Skill 证据索引。
- `semantic-loss-ledger.json`：不支持、近似、未验证与需人工语义。
- `next-actions.yaml`：下游 Batch、升级、试点或阻断建议。

## Orchestration constraints

- 子 Skill 可并行执行，但存在数据依赖时必须按 `catalog.yaml` 顺序或任务图执行。
- 所有模型输出都只是候选，必须经过本 Batch 对应的客观工具门禁。
- 任一阻断项不得被平均分或整体“高相似度”覆盖。
