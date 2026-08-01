---
name: pm-b05-repository-semantic-recovery
description: "将源仓库从文件集合恢复为可查询的 Repository Semantic Graph，并产出可供转换、测试和证明复用的语义资产. Precision Migration B05 contract; use for this exact assessment, transformation, validation, repair, evidence, or cutover scope."
---

# Batch 05：仓库发现与语义资产恢复
## ELMOS runtime binding

- Invoke this repository Skill as `$pm-b05-repository-semantic-recovery`.
- Immutable source identity: `batch-05-repository-semantic-recovery` in `precision-migration-b01-44` (B05).
- Runtime adapter: `semantic-recovery-and-ir`; binding state: `DECLARED`.
- Resolve and plan with `python3 scripts/precision_migration/runtime.py plan --skill pm-b05-repository-semantic-recovery`.
- Static installation and local evidence evaluation never substitute for exact source/target execution, independent review, customer acceptance, production operation, or certification; missing evidence stays `NOT_RUN`.


## Goal

将源仓库从文件集合恢复为可查询的 Repository Semantic Graph，并产出可供转换、测试和证明复用的语义资产。

## Position in the system

- Phase: `B 源码理解与可信执行底座`
- Included skills: `12`
- Required status vocabulary: `PROVED | VERIFIED | CONDITIONALLY_VERIFIED | REQUIRES_ADAPTER | REQUIRES_HUMAN_REVIEW | UNSUPPORTED | FAILED`

## Batch workflow

1. 发现仓库与环境
2. 使用原生工具提取语义
3. 建立可复现工具链和沙箱
4. 执行最小验证任务
5. 持久化摘要、哈希和证据

## Shared gates

- 不执行未隔离的客户或AI代码
- 工具链版本与镜像必须锁定
- 未能解析的动态语义必须显式标记

## Dispatch rules

- 当任务涉及 **repository-inventory-scanner** 时，调用 `../pm-b05-repository-inventory-scanner/SKILL.md`。
- 当任务涉及 **build-system-detector** 时，调用 `../pm-b05-build-system-detector/SKILL.md`。
- 当任务涉及 **dependency-and-plugin-discovery** 时，调用 `../pm-b05-dependency-and-plugin-discovery/SKILL.md`。
- 当任务涉及 **symbol-and-type-indexer** 时，调用 `../pm-b05-symbol-and-type-indexer/SKILL.md`。
- 当任务涉及 **call-graph-builder** 时，调用 `../pm-b05-call-graph-builder/SKILL.md`。
- 当任务涉及 **data-flow-graph-builder** 时，调用 `../pm-b05-data-flow-graph-builder/SKILL.md`。
- 当任务涉及 **effect-and-side-effect-discovery** 时，调用 `../pm-b05-effect-and-side-effect-discovery/SKILL.md`。
- 当任务涉及 **database-access-discovery** 时，调用 `../pm-b05-database-access-discovery/SKILL.md`。
- 当任务涉及 **external-service-discovery** 时，调用 `../pm-b05-external-service-discovery/SKILL.md`。
- 当任务涉及 **runtime-trace-fusion** 时，调用 `../pm-b05-runtime-trace-fusion/SKILL.md`。
- 当任务涉及 **semantic-slice-extractor** 时，调用 `../pm-b05-semantic-slice-extractor/SKILL.md`。
- 当任务涉及 **business-rule-extractor** 时，调用 `../pm-b05-business-rule-extractor/SKILL.md`。

## Skill catalog

| Skill | Responsibility |
|---|---|
| `repository-inventory-scanner` | 盘点源码、模块、资源、配置、脚本、生成代码、数据库对象、测试和部署资产。 |
| `build-system-detector` | 识别单仓或多仓构建系统、模块关系、版本约束、插件和构建入口。 |
| `dependency-and-plugin-discovery` | 解析直接与传递依赖、插件、许可证、原生扩展和运行时加载依赖。 |
| `symbol-and-type-indexer` | 建立跨文件符号、类型、引用、泛型实例化和源码位置索引。 |
| `call-graph-builder` | 构建静态与动态融合的调用图，并标记反射、RPC、消息和插件边。 |
| `data-flow-graph-builder` | 构建跨函数和跨模块数据流、污点流和关键业务数据传播图。 |
| `effect-and-side-effect-discovery` | 发现数据库、缓存、文件、消息、网络、时间、随机数和外部调用副作用。 |
| `database-access-discovery` | 识别 ORM、原生 SQL、存储过程、事务、锁、迁移和数据库对象依赖。 |
| `external-service-discovery` | 识别 HTTP、RPC、消息、SDK、设备和云服务集成及其契约。 |
| `runtime-trace-fusion` | 将生产或测试 Trace 与静态图融合，恢复真实路径、动态类型、调用频率和反射行为。 |
| `semantic-slice-extractor` | 围绕入口、业务能力或风险点提取最小可转换和可验证语义切片。 |
| `business-rule-extractor` | 从代码、测试、文档、数据约束和 Trace 中提取业务规则、不变量和例外。 |

## Batch outputs

- `batch-result.yaml`：批次状态、输入、产物和未解决项。
- `evidence-index.json`：所有子 Skill 证据索引。
- `semantic-loss-ledger.json`：不支持、近似、未验证与需人工语义。
- `next-actions.yaml`：下游 Batch、升级、试点或阻断建议。

## Orchestration constraints

- 子 Skill 可并行执行，但存在数据依赖时必须按 `catalog.yaml` 顺序或任务图执行。
- 所有模型输出都只是候选，必须经过本 Batch 对应的客观工具门禁。
- 任一阻断项不得被平均分或整体“高相似度”覆盖。
