---
name: pm-b11-transformation-skill-recipe
description: "把自然语言、参考文档、代码样例和专家知识编译为可版本化、可组合、可测试和可审计的 Transformation Skill. Precision Migration B11 contract; use for this exact assessment, transformation, validation, repair, evidence, or cutover scope."
---

# Batch 11：Transformation Skill与Recipe体系
## ELMOS runtime binding

- Invoke this repository Skill as `$pm-b11-transformation-skill-recipe`.
- Immutable source identity: `batch-11-transformation-skill-recipe` in `precision-migration-b01-44` (B11).
- Runtime adapter: `semantic-recovery-and-ir`; binding state: `DECLARED`.
- Resolve and plan with `python3 scripts/precision_migration/runtime.py plan --skill pm-b11-transformation-skill-recipe`.
- Static installation and local evidence evaluation never substitute for exact source/target execution, independent review, customer acceptance, production operation, or certification; missing evidence stays `NOT_RUN`.


## Goal

把自然语言、参考文档、代码样例和专家知识编译为可版本化、可组合、可测试和可审计的 Transformation Skill。

## Position in the system

- Phase: `D 转换定义与规则引擎`
- Included skills: `14`
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

- 当任务涉及 **natural-language-transformation-definition** 时，调用 `../pm-b11-natural-language-transformation-definition/SKILL.md`。
- 当任务涉及 **transformation-skill-compiler** 时，调用 `../pm-b11-transformation-skill-compiler/SKILL.md`。
- 当任务涉及 **reference-knowledge-loader** 时，调用 `../pm-b11-reference-knowledge-loader/SKILL.md`。
- 当任务涉及 **code-example-rule-induction** 时，调用 `../pm-b11-code-example-rule-induction/SKILL.md`。
- 当任务涉及 **declarative-recipe-dsl** 时，调用 `../pm-b11-declarative-recipe-dsl/SKILL.md`。
- 当任务涉及 **imperative-recipe-runtime** 时，调用 `../pm-b11-imperative-recipe-runtime/SKILL.md`。
- 当任务涉及 **recipe-precondition-engine** 时，调用 `../pm-b11-recipe-precondition-engine/SKILL.md`。
- 当任务涉及 **scanning-recipe-engine** 时，调用 `../pm-b11-scanning-recipe-engine/SKILL.md`。
- 当任务涉及 **multi-cycle-transformation-engine** 时，调用 `../pm-b11-multi-cycle-transformation-engine/SKILL.md`。
- 当任务涉及 **recipe-composition-and-ordering** 时，调用 `../pm-b11-recipe-composition-and-ordering/SKILL.md`。
- 当任务涉及 **recipe-versioning** 时，调用 `../pm-b11-recipe-versioning/SKILL.md`。
- 当任务涉及 **transformation-registry** 时，调用 `../pm-b11-transformation-registry/SKILL.md`。
- 当任务涉及 **managed-transformation-pack** 时，调用 `../pm-b11-managed-transformation-pack/SKILL.md`。
- 当任务涉及 **organization-private-transformation-pack** 时，调用 `../pm-b11-organization-private-transformation-pack/SKILL.md`。

## Skill catalog

| Skill | Responsibility |
|---|---|
| `natural-language-transformation-definition` | 将目标、范围、前置条件、例外、禁止项和验收要求结构化为转换定义。 |
| `transformation-skill-compiler` | 把 Transformation Skill 编译为规则、查询、生成器、验证器和证据要求。 |
| `reference-knowledge-loader` | 加载文档、API、版本说明、组织规范和历史迁移知识，并保持来源可追踪。 |
| `code-example-rule-induction` | 从正反代码样例、失败案例和人工修复中归纳候选规则及适用条件。 |
| `declarative-recipe-dsl` | 定义模式匹配、类型条件、重写、证明义务、测试和版本兼容的声明式 DSL。 |
| `imperative-recipe-runtime` | 运行需要全局分析、多文件状态或复杂生成逻辑的命令式 Recipe。 |
| `recipe-precondition-engine` | 在执行重写前验证类型、框架、版本、控制流和语义前置条件。 |
| `scanning-recipe-engine` | 先扫描全仓库收集状态，再执行跨文件和跨模块变换。 |
| `multi-cycle-transformation-engine` | 支持扫描、变换、构建反馈、再扫描和多轮收敛。 |
| `recipe-composition-and-ordering` | 解决规则依赖、顺序、冲突、幂等和可交换性。 |
| `recipe-versioning` | 管理规则语义版本、适用矩阵、迁移升级和回归兼容。 |
| `transformation-registry` | 登记、发现、签名、授权、发布和撤回转换技能与方向包。 |
| `managed-transformation-pack` | 封装平台维护、经过验证、可规模复用的托管转换包。 |
| `organization-private-transformation-pack` | 封装客户私有框架、内部 API、命名规范和受限知识的专属转换包。 |

## Batch outputs

- `batch-result.yaml`：批次状态、输入、产物和未解决项。
- `evidence-index.json`：所有子 Skill 证据索引。
- `semantic-loss-ledger.json`：不支持、近似、未验证与需人工语义。
- `next-actions.yaml`：下游 Batch、升级、试点或阻断建议。

## Orchestration constraints

- 子 Skill 可并行执行，但存在数据依赖时必须按 `catalog.yaml` 顺序或任务图执行。
- 所有模型输出都只是候选，必须经过本 Batch 对应的客观工具门禁。
- 任一阻断项不得被平均分或整体“高相似度”覆盖。
