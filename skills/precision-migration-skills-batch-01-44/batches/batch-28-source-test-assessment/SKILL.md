---
name: batch-28-source-test-assessment
description: 盘点源测试并判断其覆盖范围、Oracle可信度、断言强度、稳定性和迁移价值。
---

# Batch 28：源测试资产评估

## Goal

盘点源测试并判断其覆盖范围、Oracle可信度、断言强度、稳定性和迁移价值。

## Position in the system

- Phase: `H 测试、验证与自动修复`
- Included skills: `8`
- Required status vocabulary: `PROVED | VERIFIED | CONDITIONALLY_VERIFIED | REQUIRES_ADAPTER | REQUIRES_HUMAN_REVIEW | UNSUPPORTED | FAILED`

## Batch workflow

1. 评估或生成测试
2. 同步环境并双运行
3. 比较输出、状态和副作用
4. 搜索最小反例
5. 驱动修复并执行全量回归

## Shared gates

- 未解释差异必须阻断
- 测试弱化和删除必须阻断
- 关键不变量、权限和不可逆副作用必须100%通过

## Dispatch rules

- 当任务涉及 **source-test-inventory** 时，调用 `skills/source-test-inventory/SKILL.md`。
- 当任务涉及 **test-coverage-normalizer** 时，调用 `skills/test-coverage-normalizer/SKILL.md`。
- 当任务涉及 **assertion-quality-analyzer** 时，调用 `skills/assertion-quality-analyzer/SKILL.md`。
- 当任务涉及 **skipped-and-flaky-test-detector** 时，调用 `skills/skipped-and-flaky-test-detector/SKILL.md`。
- 当任务涉及 **test-oracle-classifier** 时，调用 `skills/test-oracle-classifier/SKILL.md`。
- 当任务涉及 **test-mutation-strength-assessment** 时，调用 `skills/test-mutation-strength-assessment/SKILL.md`。
- 当任务涉及 **missing-test-gap-analysis** 时，调用 `skills/missing-test-gap-analysis/SKILL.md`。
- 当任务涉及 **test-migration-feasibility** 时，调用 `skills/test-migration-feasibility/SKILL.md`。

## Skill catalog

| Skill | Responsibility |
|---|---|
| `source-test-inventory` | 盘点单元、集成、契约、E2E、性能、安全、数据和设备测试。 |
| `test-coverage-normalizer` | 统一语句、分支、路径、接口、状态、Effect、Journey 和风险覆盖指标。 |
| `assertion-quality-analyzer` | 检测无断言、弱断言、仅状态码、过度快照和未验证副作用等问题。 |
| `skipped-and-flaky-test-detector` | 识别跳过、条件跳过、重试掩盖、时间依赖和环境不稳定测试。 |
| `test-oracle-classifier` | 标注 Oracle 来源为源运行、源测试、规格、业务规则、Trace、形式规格或 AI 推断。 |
| `test-mutation-strength-assessment` | 通过通用和方向专用变异衡量测试能否发现真实转换错误。 |
| `missing-test-gap-analysis` | 按接口、状态、错误、权限、数据、副作用、并发、故障和 Journey 找缺口。 |
| `test-migration-feasibility` | 判断哪些测试可直接迁移、需重写、需双运行或不可复用。 |

## Batch outputs

- `batch-result.yaml`：批次状态、输入、产物和未解决项。
- `evidence-index.json`：所有子 Skill 证据索引。
- `semantic-loss-ledger.json`：不支持、近似、未验证与需人工语义。
- `next-actions.yaml`：下游 Batch、升级、试点或阻断建议。

## Orchestration constraints

- 子 Skill 可并行执行，但存在数据依赖时必须按 `catalog.yaml` 顺序或任务图执行。
- 所有模型输出都只是候选，必须经过本 Batch 对应的客观工具门禁。
- 任一阻断项不得被平均分或整体“高相似度”覆盖。
