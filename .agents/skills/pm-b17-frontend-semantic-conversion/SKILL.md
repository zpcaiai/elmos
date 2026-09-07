---
name: pm-b17-frontend-semantic-conversion
description: "恢复前端组件、响应式依赖、UI状态机、事件、布局、路由和平台能力，作为跨框架和跨平台转换的共同语义层. Precision Migration B17 contract; use for this exact assessment, transformation, validation, repair, evidence, or cutover scope."
---

# Batch 17：Frontend UI Semantic Conversion
## ELMOS runtime binding

- Invoke this repository Skill as `$pm-b17-frontend-semantic-conversion`.
- Immutable source identity: `batch-17-frontend-semantic-conversion` in `precision-migration-b01-44` (B17).
- Runtime adapter: `frontend-client-route`; binding state: `DECLARED`.
- Resolve and plan with `python3 scripts/precision_migration/runtime.py plan --skill pm-b17-frontend-semantic-conversion`.
- Static installation and local evidence evaluation never substitute for exact source/target execution, independent review, customer acceptance, production operation, or certification; missing evidence stays `NOT_RUN`.


## Goal

恢复前端组件、响应式依赖、UI状态机、事件、布局、路由和平台能力，作为跨框架和跨平台转换的共同语义层。

## Position in the system

- Phase: `F 前端与多端互转`
- Included skills: `12`
- Required status vocabulary: `PROVED | VERIFIED | CONDITIONALLY_VERIFIED | REQUIRES_ADAPTER | REQUIRES_HUMAN_REVIEW | UNSUPPORTED | FAILED`

## Batch workflow

1. 恢复组件契约和UI状态机
2. 映射事件、路由、布局和平台能力
3. 生成目标项目
4. 执行语义树、Journey和网络差分
5. 执行视觉/真机验证并修复

## Shared gates

- 不能用源码相似度替代行为一致
- 平台能力缺失必须给适配或明确不支持
- 关键Journey必须100%通过

## Dispatch rules

- 当任务涉及 **component-contract-recovery** 时，调用 `../pm-b17-component-contract-recovery/SKILL.md`。
- 当任务涉及 **reactive-dependency-analysis** 时，调用 `../pm-b17-reactive-dependency-analysis/SKILL.md`。
- 当任务涉及 **ui-state-machine-recovery** 时，调用 `../pm-b17-ui-state-machine-recovery/SKILL.md`。
- 当任务涉及 **event-effect-trace-recovery** 时，调用 `../pm-b17-event-effect-trace-recovery/SKILL.md`。
- 当任务涉及 **lifecycle-semantic-mapping** 时，调用 `../pm-b17-lifecycle-semantic-mapping/SKILL.md`。
- 当任务涉及 **slot-children-content-mapping** 时，调用 `../pm-b17-slot-children-content-mapping/SKILL.md`。
- 当任务涉及 **form-validation-mapping** 时，调用 `../pm-b17-form-validation-mapping/SKILL.md`。
- 当任务涉及 **route-navigation-mapping** 时，调用 `../pm-b17-route-navigation-mapping/SKILL.md`。
- 当任务涉及 **network-request-semantic-mapping** 时，调用 `../pm-b17-network-request-semantic-mapping/SKILL.md`。
- 当任务涉及 **local-storage-mapping** 时，调用 `../pm-b17-local-storage-mapping/SKILL.md`。
- 当任务涉及 **layout-constraint-mapping** 时，调用 `../pm-b17-layout-constraint-mapping/SKILL.md`。
- 当任务涉及 **accessibility-semantic-tree** 时，调用 `../pm-b17-accessibility-semantic-tree/SKILL.md`。

## Skill catalog

| Skill | Responsibility |
|---|---|
| `component-contract-recovery` | 恢复 Props、Events、Slots/Children、公开方法、Context 和组件边界契约。 |
| `reactive-dependency-analysis` | 分析响应式读写、Computed、Watcher、Hook 依赖、派生状态和闭包捕获。 |
| `ui-state-machine-recovery` | 从组件和流程恢复 Idle、Loading、Success、Failure、Submitting 等状态机。 |
| `event-effect-trace-recovery` | 恢复用户事件、网络、存储、导航、定时器和平台调用的 Effect Trace。 |
| `lifecycle-semantic-mapping` | 映射 Vue、React、小程序、ArkUI 和 Flutter 生命周期及清理语义。 |
| `slot-children-content-mapping` | 映射 Slot、Scoped Slot、Children、Render Props、Builder 和内容投影。 |
| `form-validation-mapping` | 映射表单字段、校验、触摸状态、错误显示、提交与异步校验。 |
| `route-navigation-mapping` | 映射路由、参数、守卫、返回栈、Tab、深链接和页面恢复。 |
| `network-request-semantic-mapping` | 映射请求序列化、取消、重试、缓存、错误、竞态和 Latest-wins。 |
| `local-storage-mapping` | 映射 Cookie、LocalStorage、IndexedDB、SharedPreferences 和平台安全存储。 |
| `layout-constraint-mapping` | 把 DOM/CSS、Flex/Grid、Widget、ArkUI 和小程序布局映射到约束 IR。 |
| `accessibility-semantic-tree` | 提取并比较 Role、Name、State、Value、Focus 和可操作性语义树。 |

## Batch outputs

- `batch-result.yaml`：批次状态、输入、产物和未解决项。
- `evidence-index.json`：所有子 Skill 证据索引。
- `semantic-loss-ledger.json`：不支持、近似、未验证与需人工语义。
- `next-actions.yaml`：下游 Batch、升级、试点或阻断建议。

## Orchestration constraints

- 子 Skill 可并行执行，但存在数据依赖时必须按 `catalog.yaml` 顺序或任务图执行。
- 所有模型输出都只是候选，必须经过本 Batch 对应的客观工具门禁。
- 任一阻断项不得被平均分或整体“高相似度”覆盖。
