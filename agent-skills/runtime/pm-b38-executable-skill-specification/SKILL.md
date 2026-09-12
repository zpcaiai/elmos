---
name: pm-b38-executable-skill-specification
description: "将自然语言 Skill 提升为可版本化、可组合、可验证的执行规格、领域模型、状态机、生成器和验收包. Precision Migration B38 contract; use for this exact assessment, transformation, validation, repair, evidence, or cutover scope."
---

# Batch 38：Executable Skill规范
## ELMOS runtime binding

- Invoke this repository Skill as `$pm-b38-executable-skill-specification`.
- Immutable source identity: `batch-38-executable-skill-specification` in `precision-migration-b01-44` (B38).
- Runtime adapter: `skill-and-project-synthesis`; binding state: `DECLARED`.
- Resolve and plan with `python3 scripts/precision_migration/runtime.py plan --skill pm-b38-executable-skill-specification`.
- Static installation and local evidence evaluation never substitute for exact source/target execution, independent review, customer acceptance, production operation, or certification; missing evidence stays `NOT_RUN`.


## Goal

将自然语言 Skill 提升为可版本化、可组合、可验证的执行规格、领域模型、状态机、生成器和验收包。

## Position in the system

- Phase: `K 从Skills生成完整项目`
- Included skills: `10`
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

- 当任务涉及 **skill-schema-validator** 时，调用 `../pm-b38-skill-schema-validator/SKILL.md`。
- 当任务涉及 **skill-dependency-resolver** 时，调用 `../pm-b38-skill-dependency-resolver/SKILL.md`。
- 当任务涉及 **skill-conflict-detector** 时，调用 `../pm-b38-skill-conflict-detector/SKILL.md`。
- 当任务涉及 **skill-composition-planner** 时，调用 `../pm-b38-skill-composition-planner/SKILL.md`。
- 当任务涉及 **behavior-contract-compiler** 时，调用 `../pm-b38-behavior-contract-compiler/SKILL.md`。
- 当任务涉及 **acceptance-test-compiler** 时，调用 `../pm-b38-acceptance-test-compiler/SKILL.md`。
- 当任务涉及 **domain-model-compiler** 时，调用 `../pm-b38-domain-model-compiler/SKILL.md`。
- 当任务涉及 **state-machine-compiler** 时，调用 `../pm-b38-state-machine-compiler/SKILL.md`。
- 当任务涉及 **skill-version-compatibility** 时，调用 `../pm-b38-skill-version-compatibility/SKILL.md`。
- 当任务涉及 **skill-marketplace-package** 时，调用 `../pm-b38-skill-marketplace-package/SKILL.md`。

## Skill catalog

| Skill | Responsibility |
|---|---|
| `skill-schema-validator` | 验证 Skill 元数据、输入输出、前置条件、行为契约、测试和兼容声明。 |
| `skill-dependency-resolver` | 解析 Skill 依赖、版本范围、传递依赖、可选能力和安装顺序。 |
| `skill-conflict-detector` | 发现领域、Schema、权限、状态、资源、路由和依赖冲突。 |
| `skill-composition-planner` | 生成满足依赖、顺序、隔离和共享能力的 Skill 组合执行计划。 |
| `behavior-contract-compiler` | 把 Skill 业务规则编译为类型、Effect、状态、接口和验证契约。 |
| `acceptance-test-compiler` | 把 Skill 验收场景编译为单元、契约、E2E、属性和门禁测试。 |
| `domain-model-compiler` | 把实体、值对象、关系、不变量和事件编译为语言无关领域模型。 |
| `state-machine-compiler` | 把业务和 UI 状态机编译为生成器、运行时检查和形式义务。 |
| `skill-version-compatibility` | 检查 Skill 升级、降级、数据迁移、依赖和生成代码兼容性。 |
| `skill-marketplace-package` | 打包签名、许可证、权限、安装、升级、示例、证据和发布元数据。 |

## Batch outputs

- `batch-result.yaml`：批次状态、输入、产物和未解决项。
- `evidence-index.json`：所有子 Skill 证据索引。
- `semantic-loss-ledger.json`：不支持、近似、未验证与需人工语义。
- `next-actions.yaml`：下游 Batch、升级、试点或阻断建议。

## Orchestration constraints

- 子 Skill 可并行执行，但存在数据依赖时必须按 `catalog.yaml` 顺序或任务图执行。
- 所有模型输出都只是候选，必须经过本 Batch 对应的客观工具门禁。
- 任一阻断项不得被平均分或整体“高相似度”覆盖。
