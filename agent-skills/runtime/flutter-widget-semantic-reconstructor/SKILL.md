---
name: flutter-widget-semantic-reconstructor
description: Reconstruct Flutter/Dart widget trees, navigation, state management,
  gestures, themes, animations, painters, and platform channels into MiniApp IR. Use
  for Flutter sources; never convert by screenshotting or flattening the whole UI
  to Canvas.
license: Proprietary
metadata:
  package: elmos.frontend-to-miniapp.skills
  version: 1.0.0
  stage: source-analysis
  task_ids:
  - MAPP-009
  - MAPP-010
  maturity: implementation-ready
---

# flutter-widget-semantic-reconstructor

## 目标

通过 Dart 静态分析恢复 Widget、状态和导航语义，而不是对 Dart 做文本级替换。

## 何时使用

- 检测到 pubspec.yaml 或 Flutter 工程
- 需要处理 Widget、Provider/Riverpod/Bloc/GetX 或 Platform Channel

## 输入

- Flutter 工程、pubspec.lock、Dart 分析配置
- project-inventory.json

输入必须来自固定的仓库修订或带内容哈希的任务产物。发现缺失字段时，先输出结构化阻断项；不要凭空补齐平台权限、业务规则或凭证。

## 输出

- flutter-analysis.json
- widget-tree.json
- navigation-graph.json
- state-graph.json
- platform-channel-report.json

所有 JSON 输出必须通过本包 `schemas/` 中对应的 Draft 2020-12 Schema；所有生成文件必须进入 artifact index，并记录源修订、规则版本与内容哈希。

## 依赖技能

- miniapp-source-framework-detector

## 执行流程

1. 运行只读 Dart analyzer，解析 library、class、constructor、类型和常量。
2. 识别 StatelessWidget、StatefulWidget、State 生命周期和 build 依赖。
3. 重建常见 Widget Tree、布局约束、主题、资源与本地化。
4. 解析 Navigator、Router API、命名路由、参数和返回值。
5. 识别 Provider、Riverpod、Bloc/Cubit、GetX 等状态流和副作用。
6. 将 GestureDetector、表单、动画、CustomPainter 与平台插件映射为语义能力。
7. 对 Platform Channel、原生插件、Shader 和复杂渲染给出替代策略与风险。
8. 输出禁止降级项，除非 conversion-request 明确允许 Canvas/WebView。

## 强制规则

- 不得整页截图化
- 不得默认整页 Canvas 化
- CustomPainter 必须逐项分析是否可由原生组件、Canvas 局部或资源替代

通用规则：

- 不得声称“转换完成”而没有编译、测试和证据。
- 不得在客户端代码、日志、报告或 fixture 中写入真实平台密钥。
- 不得静默删除功能、事件、权限、数据流或错误处理。
- 生成步骤必须确定性；同一输入和规则版本应产生相同规范化输出。
- 外部工具链、账户权限、平台审核或真实支付不可用时，输出 `blocked` 及证据，不得伪造成功。
- 任何有副作用的动作必须有幂等键、审批状态和回滚/补偿策略。

## 验收门禁

- 主要页面 Widget Tree 可重建
- 导航图闭合
- 插件与 Platform Channel 100% 有结论

## 常见失败与升级条件

- 代码生成缺失
- 运行时反射或动态 Widget
- 私有原生插件
- 复杂 GPU Shader

遇到以下任一条件必须停止自动执行并升级到 orchestrator：需要真实支付/退款/发布、需要扩大权限、需要降低安全或质量门禁、连续两次产生等价补丁、达到最大修复次数、或无法证明行为等价。

## 任务追踪

- 任务 ID：MAPP-009, MAPP-010
- 输出状态：`not_started | running | blocked | failed | passed | approved`
- 每次执行记录：输入哈希、输出哈希、工具版本、开始/结束时间、系统墙钟运行时、成本、失败分类与下一恢复点。
- 不使用人工人日替代系统实际运行时；需要 ETA 时报告机器墙钟 ETA 及置信区间。

## 附带资源

- `references/contract.md`：接口、幂等、可观测性和测试契约。
- `assets/output-contract.yaml`：本技能要求的输出文件与最低门禁。
- `examples/invocation.md`：Codex 与 Claude Code 调用示例。
- 包级 Schema、模板和实施文档位于仓库根目录的 `schemas/`、`templates/`、`docs/`。

## 完成定义

只有当本技能的全部必需输出存在、Schema 验证通过、门禁结果有证据、阻断项被显式披露，并且上游 orchestrator 已接收 artifact index 后，状态才可标记为 `passed`。

## Repository Integration Boundary

- Source identity is pinned to `elmos.frontend-to-miniapp.skills` `1.0.0`, Skill `flutter-widget-semantic-reconstructor`, and `sha256:8caf1ce12871b2b8ab2052dd7ef359666e723bfda67231e662c7ee5c8075411f`.
- The source label `implementation-ready` describes package intent only. The repository handler bytes are present but no valid local qualification receipt exists, so runtime evidence is `DECLARED`; external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Local contracts, parsers, typed IR, planners, four candidate generators, handlers, CLI, checkpoints and fail-closed tests are implemented. They do not prove an official-toolchain build, emulator/device journey, visual or behavior equivalence, upload, review, payment, or release.
- Runtime dispatch is owned by `engines/frontend-client-engine`: `npm run miniapp` (`dist/src/miniapp-cli.js`), structured handler `handleMiniappSkillRequest`, JSON handler `runMiniappSkillJson`, full flow `runMiniappConversion`, strict package flow `runMiniappPackageConversion`, and single-Skill handler `executeMiniappSkill` with Skill key `flutter-widget-semantic-reconstructor`.
- The canonical snake_case request at `skills/elmos-frontend-to-miniapp-skills-v1.0.0/schemas/conversion-request.schema.json` is callable as `npm run miniapp -- package`; handler action `run-package` receives `packageInput` and invokes `validateMiniappPackageConversionInput` then `compileMiniappPackageConversionInput` without disk discovery or package-script execution.
- Component analysis/emission is an explicit downstream adapter at `engines/component-dialect-engine`: `npm run miniapp-worker` (`dist/miniapp-worker.js`), `handleMiniAppWorkerRequest` / `runMiniAppWorkerJson`, emitter `emitPlatformMiniApp`.
- Every route remains directional and exact to source framework/runtime/providers and target MiniApp platform/toolchain/API versions. A reverse MiniApp-to-frontend route is separate and is not implied.
- Transform through typed UI Interaction/MiniApp Semantic IR with source traces. Regex, screenshot, WebView, full-page Canvas, silent feature drops, weakened tests, or widened permissions cannot establish equivalence.
- Real source and target builds, browser/emulator/device journeys, negative and independent holdout corpora, accessibility, privacy, permission, visual, business, and rollback evidence remain required.
- Platform credentials are references only. Upload, review, payment, refund, release, and other side effects require separate authorization and auditable idempotency controls.
- Only the conservative Batch 32 client gate may raise readiness; static package validation cannot certify this Skill.
