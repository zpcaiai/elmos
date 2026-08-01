---
name: batch-18-frontend-direction-packs
description: 为 Vue 2、Vue 3、React、微信小程序、ArkUI、Flutter 的 30 条有方向路径及两类现代化路径维护专用规则与验证。
---

# Batch 18：前端方向转换包

## Goal

为 Vue 2、Vue 3、React、微信小程序、ArkUI、Flutter 的 30 条有方向路径及两类现代化路径维护专用规则与验证。

## Position in the system

- Phase: `F 前端与多端互转`
- Included skills: `32`
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

- 当任务涉及 **vue2-to-vue3-direction-pack** 时，调用 `skills/vue2-to-vue3-direction-pack/SKILL.md`。
- 当任务涉及 **vue2-to-react-direction-pack** 时，调用 `skills/vue2-to-react-direction-pack/SKILL.md`。
- 当任务涉及 **vue2-to-wechat-miniprogram-direction-pack** 时，调用 `skills/vue2-to-wechat-miniprogram-direction-pack/SKILL.md`。
- 当任务涉及 **vue2-to-arkui-direction-pack** 时，调用 `skills/vue2-to-arkui-direction-pack/SKILL.md`。
- 当任务涉及 **vue2-to-flutter-direction-pack** 时，调用 `skills/vue2-to-flutter-direction-pack/SKILL.md`。
- 当任务涉及 **vue3-to-vue2-direction-pack** 时，调用 `skills/vue3-to-vue2-direction-pack/SKILL.md`。
- 当任务涉及 **vue3-to-react-direction-pack** 时，调用 `skills/vue3-to-react-direction-pack/SKILL.md`。
- 当任务涉及 **vue3-to-wechat-miniprogram-direction-pack** 时，调用 `skills/vue3-to-wechat-miniprogram-direction-pack/SKILL.md`。
- 当任务涉及 **vue3-to-arkui-direction-pack** 时，调用 `skills/vue3-to-arkui-direction-pack/SKILL.md`。
- 当任务涉及 **vue3-to-flutter-direction-pack** 时，调用 `skills/vue3-to-flutter-direction-pack/SKILL.md`。
- 当任务涉及 **react-to-vue2-direction-pack** 时，调用 `skills/react-to-vue2-direction-pack/SKILL.md`。
- 当任务涉及 **react-to-vue3-direction-pack** 时，调用 `skills/react-to-vue3-direction-pack/SKILL.md`。
- 当任务涉及 **react-to-wechat-miniprogram-direction-pack** 时，调用 `skills/react-to-wechat-miniprogram-direction-pack/SKILL.md`。
- 当任务涉及 **react-to-arkui-direction-pack** 时，调用 `skills/react-to-arkui-direction-pack/SKILL.md`。
- 当任务涉及 **react-to-flutter-direction-pack** 时，调用 `skills/react-to-flutter-direction-pack/SKILL.md`。
- 当任务涉及 **wechat-miniprogram-to-vue2-direction-pack** 时，调用 `skills/wechat-miniprogram-to-vue2-direction-pack/SKILL.md`。
- 当任务涉及 **wechat-miniprogram-to-vue3-direction-pack** 时，调用 `skills/wechat-miniprogram-to-vue3-direction-pack/SKILL.md`。
- 当任务涉及 **wechat-miniprogram-to-react-direction-pack** 时，调用 `skills/wechat-miniprogram-to-react-direction-pack/SKILL.md`。
- 当任务涉及 **wechat-miniprogram-to-arkui-direction-pack** 时，调用 `skills/wechat-miniprogram-to-arkui-direction-pack/SKILL.md`。
- 当任务涉及 **wechat-miniprogram-to-flutter-direction-pack** 时，调用 `skills/wechat-miniprogram-to-flutter-direction-pack/SKILL.md`。
- 当任务涉及 **arkui-to-vue2-direction-pack** 时，调用 `skills/arkui-to-vue2-direction-pack/SKILL.md`。
- 当任务涉及 **arkui-to-vue3-direction-pack** 时，调用 `skills/arkui-to-vue3-direction-pack/SKILL.md`。
- 当任务涉及 **arkui-to-react-direction-pack** 时，调用 `skills/arkui-to-react-direction-pack/SKILL.md`。
- 当任务涉及 **arkui-to-wechat-miniprogram-direction-pack** 时，调用 `skills/arkui-to-wechat-miniprogram-direction-pack/SKILL.md`。
- 当任务涉及 **arkui-to-flutter-direction-pack** 时，调用 `skills/arkui-to-flutter-direction-pack/SKILL.md`。
- 当任务涉及 **flutter-to-vue2-direction-pack** 时，调用 `skills/flutter-to-vue2-direction-pack/SKILL.md`。
- 当任务涉及 **flutter-to-vue3-direction-pack** 时，调用 `skills/flutter-to-vue3-direction-pack/SKILL.md`。
- 当任务涉及 **flutter-to-react-direction-pack** 时，调用 `skills/flutter-to-react-direction-pack/SKILL.md`。
- 当任务涉及 **flutter-to-wechat-miniprogram-direction-pack** 时，调用 `skills/flutter-to-wechat-miniprogram-direction-pack/SKILL.md`。
- 当任务涉及 **flutter-to-arkui-direction-pack** 时，调用 `skills/flutter-to-arkui-direction-pack/SKILL.md`。
- 当任务涉及 **javascript-to-typescript-modernization-pack** 时，调用 `skills/javascript-to-typescript-modernization-pack/SKILL.md`。
- 当任务涉及 **react-class-to-hooks-modernization-pack** 时，调用 `skills/react-class-to-hooks-modernization-pack/SKILL.md`。

## Skill catalog

| Skill | Responsibility |
|---|---|
| `vue2-to-vue3-direction-pack` | 提供从 Vue 2 到 Vue 3 的前端整库专用转换与验证包，覆盖组件、状态、生命周期、路由、布局、平台能力和真机行为。 |
| `vue2-to-react-direction-pack` | 提供从 Vue 2 到 React 的前端整库专用转换与验证包，覆盖组件、状态、生命周期、路由、布局、平台能力和真机行为。 |
| `vue2-to-wechat-miniprogram-direction-pack` | 提供从 Vue 2 到 微信小程序 的前端整库专用转换与验证包，覆盖组件、状态、生命周期、路由、布局、平台能力和真机行为。 |
| `vue2-to-arkui-direction-pack` | 提供从 Vue 2 到 ArkTS/ArkUI 的前端整库专用转换与验证包，覆盖组件、状态、生命周期、路由、布局、平台能力和真机行为。 |
| `vue2-to-flutter-direction-pack` | 提供从 Vue 2 到 Flutter 的前端整库专用转换与验证包，覆盖组件、状态、生命周期、路由、布局、平台能力和真机行为。 |
| `vue3-to-vue2-direction-pack` | 提供从 Vue 3 到 Vue 2 的前端整库专用转换与验证包，覆盖组件、状态、生命周期、路由、布局、平台能力和真机行为。 |
| `vue3-to-react-direction-pack` | 提供从 Vue 3 到 React 的前端整库专用转换与验证包，覆盖组件、状态、生命周期、路由、布局、平台能力和真机行为。 |
| `vue3-to-wechat-miniprogram-direction-pack` | 提供从 Vue 3 到 微信小程序 的前端整库专用转换与验证包，覆盖组件、状态、生命周期、路由、布局、平台能力和真机行为。 |
| `vue3-to-arkui-direction-pack` | 提供从 Vue 3 到 ArkTS/ArkUI 的前端整库专用转换与验证包，覆盖组件、状态、生命周期、路由、布局、平台能力和真机行为。 |
| `vue3-to-flutter-direction-pack` | 提供从 Vue 3 到 Flutter 的前端整库专用转换与验证包，覆盖组件、状态、生命周期、路由、布局、平台能力和真机行为。 |
| `react-to-vue2-direction-pack` | 提供从 React 到 Vue 2 的前端整库专用转换与验证包，覆盖组件、状态、生命周期、路由、布局、平台能力和真机行为。 |
| `react-to-vue3-direction-pack` | 提供从 React 到 Vue 3 的前端整库专用转换与验证包，覆盖组件、状态、生命周期、路由、布局、平台能力和真机行为。 |
| `react-to-wechat-miniprogram-direction-pack` | 提供从 React 到 微信小程序 的前端整库专用转换与验证包，覆盖组件、状态、生命周期、路由、布局、平台能力和真机行为。 |
| `react-to-arkui-direction-pack` | 提供从 React 到 ArkTS/ArkUI 的前端整库专用转换与验证包，覆盖组件、状态、生命周期、路由、布局、平台能力和真机行为。 |
| `react-to-flutter-direction-pack` | 提供从 React 到 Flutter 的前端整库专用转换与验证包，覆盖组件、状态、生命周期、路由、布局、平台能力和真机行为。 |
| `wechat-miniprogram-to-vue2-direction-pack` | 提供从 微信小程序 到 Vue 2 的前端整库专用转换与验证包，覆盖组件、状态、生命周期、路由、布局、平台能力和真机行为。 |
| `wechat-miniprogram-to-vue3-direction-pack` | 提供从 微信小程序 到 Vue 3 的前端整库专用转换与验证包，覆盖组件、状态、生命周期、路由、布局、平台能力和真机行为。 |
| `wechat-miniprogram-to-react-direction-pack` | 提供从 微信小程序 到 React 的前端整库专用转换与验证包，覆盖组件、状态、生命周期、路由、布局、平台能力和真机行为。 |
| `wechat-miniprogram-to-arkui-direction-pack` | 提供从 微信小程序 到 ArkTS/ArkUI 的前端整库专用转换与验证包，覆盖组件、状态、生命周期、路由、布局、平台能力和真机行为。 |
| `wechat-miniprogram-to-flutter-direction-pack` | 提供从 微信小程序 到 Flutter 的前端整库专用转换与验证包，覆盖组件、状态、生命周期、路由、布局、平台能力和真机行为。 |
| `arkui-to-vue2-direction-pack` | 提供从 ArkTS/ArkUI 到 Vue 2 的前端整库专用转换与验证包，覆盖组件、状态、生命周期、路由、布局、平台能力和真机行为。 |
| `arkui-to-vue3-direction-pack` | 提供从 ArkTS/ArkUI 到 Vue 3 的前端整库专用转换与验证包，覆盖组件、状态、生命周期、路由、布局、平台能力和真机行为。 |
| `arkui-to-react-direction-pack` | 提供从 ArkTS/ArkUI 到 React 的前端整库专用转换与验证包，覆盖组件、状态、生命周期、路由、布局、平台能力和真机行为。 |
| `arkui-to-wechat-miniprogram-direction-pack` | 提供从 ArkTS/ArkUI 到 微信小程序 的前端整库专用转换与验证包，覆盖组件、状态、生命周期、路由、布局、平台能力和真机行为。 |
| `arkui-to-flutter-direction-pack` | 提供从 ArkTS/ArkUI 到 Flutter 的前端整库专用转换与验证包，覆盖组件、状态、生命周期、路由、布局、平台能力和真机行为。 |
| `flutter-to-vue2-direction-pack` | 提供从 Flutter 到 Vue 2 的前端整库专用转换与验证包，覆盖组件、状态、生命周期、路由、布局、平台能力和真机行为。 |
| `flutter-to-vue3-direction-pack` | 提供从 Flutter 到 Vue 3 的前端整库专用转换与验证包，覆盖组件、状态、生命周期、路由、布局、平台能力和真机行为。 |
| `flutter-to-react-direction-pack` | 提供从 Flutter 到 React 的前端整库专用转换与验证包，覆盖组件、状态、生命周期、路由、布局、平台能力和真机行为。 |
| `flutter-to-wechat-miniprogram-direction-pack` | 提供从 Flutter 到 微信小程序 的前端整库专用转换与验证包，覆盖组件、状态、生命周期、路由、布局、平台能力和真机行为。 |
| `flutter-to-arkui-direction-pack` | 提供从 Flutter 到 ArkTS/ArkUI 的前端整库专用转换与验证包，覆盖组件、状态、生命周期、路由、布局、平台能力和真机行为。 |
| `javascript-to-typescript-modernization-pack` | 将 JavaScript 仓库迁移为严格 TypeScript，恢复类型、对象 Shape、Nullability 和运行时校验。 |
| `react-class-to-hooks-modernization-pack` | 将 React Class 组件迁移为函数组件与 Hooks，并验证生命周期、闭包、Effect 和取消语义。 |

## Batch outputs

- `batch-result.yaml`：批次状态、输入、产物和未解决项。
- `evidence-index.json`：所有子 Skill 证据索引。
- `semantic-loss-ledger.json`：不支持、近似、未验证与需人工语义。
- `next-actions.yaml`：下游 Batch、升级、试点或阻断建议。

## Orchestration constraints

- 子 Skill 可并行执行，但存在数据依赖时必须按 `catalog.yaml` 顺序或任务图执行。
- 所有模型输出都只是候选，必须经过本 Batch 对应的客观工具门禁。
- 任一阻断项不得被平均分或整体“高相似度”覆盖。
