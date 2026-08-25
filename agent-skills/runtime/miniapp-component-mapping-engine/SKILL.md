---
name: miniapp-component-mapping-engine
description: Map semantic UI roles and third-party components to native miniapp components
  or generated composites with prop, event, slot, accessibility, and behavior contracts.
  Use after IR validation and before code generation.
license: Proprietary
metadata:
  package: elmos.frontend-to-miniapp.skills
  version: 1.0.0
  stage: planning
  task_ids:
  - MAPP-015
  - MAPP-016
  maturity: implementation-ready
---

# miniapp-component-mapping-engine

## 目标

以规则 DSL 选择原生组件、组合组件或受控重构，避免逐文件硬编码映射。

## 何时使用

- 需要将组件树下降到目标平台
- 新增 UI 库或平台组件映射
- 组件行为差异导致测试失败

## 输入

- semantic-ir.json
- component mapping registry
- target platform profile
- design constraints

输入必须来自固定的仓库修订或带内容哈希的任务产物。发现缺失字段时，先输出结构化阻断项；不要凭空补齐平台权限、业务规则或凭证。

## 输出

- component-mapping-plan.json
- generated-component-specs.json
- mapping-decisions.json

所有 JSON 输出必须通过本包 `schemas/` 中对应的 Draft 2020-12 Schema；所有生成文件必须进入 artifact index，并记录源修订、规则版本与内容哈希。

## 依赖技能

- miniapp-semantic-ir
- miniapp-capability-registry

## 执行流程

1. 按 semantic_role、属性、事件、插槽、布局和无障碍要求匹配候选。
2. 优先目标平台原生组件，其次生成受测组合组件，再次才是明确批准的降级。
3. 转换 props、双向绑定、事件冒泡、slot/render-prop 和受控/非受控状态。
4. 评估第三方 UI 组件的替代、重写、拆分或平台专属实现。
5. 对复杂表格、富文本、虚拟列表、弹层、手势和媒体组件建立行为契约。
6. 生成映射解释、目标依赖和单元测试样例。
7. 对无匹配项输出 C/D/E，不生成空占位符冒充成功。

## 强制规则

- 不允许用同名组件作为等价证据
- 事件与状态语义优先于视觉同名
- 可访问性和键盘/焦点行为需显式记录

通用规则：

- 不得声称“转换完成”而没有编译、测试和证据。
- 不得在客户端代码、日志、报告或 fixture 中写入真实平台密钥。
- 不得静默删除功能、事件、权限、数据流或错误处理。
- 生成步骤必须确定性；同一输入和规则版本应产生相同规范化输出。
- 外部工具链、账户权限、平台审核或真实支付不可用时，输出 `blocked` 及证据，不得伪造成功。
- 任何有副作用的动作必须有幂等键、审批状态和回滚/补偿策略。

## 验收门禁

- 可见组件 100% 有映射结论
- 关键交互组件有行为测试
- 无空实现

## 常见失败与升级条件

- 复杂 UI 库无替代
- 平台组件能力不足
- 动态渲染
- 无障碍语义不一致

遇到以下任一条件必须停止自动执行并升级到 orchestrator：需要真实支付/退款/发布、需要扩大权限、需要降低安全或质量门禁、连续两次产生等价补丁、达到最大修复次数、或无法证明行为等价。

## 任务追踪

- 任务 ID：MAPP-015, MAPP-016
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

- Source identity is pinned to `elmos.frontend-to-miniapp.skills` `1.0.0`, Skill `miniapp-component-mapping-engine`, and `sha256:80846c23cd754eac79020401354ef333b8817e7d966eb0c2de291c8647065c97`.
- The source label `implementation-ready` describes package intent only. The repository handler bytes are present but no valid local qualification receipt exists, so runtime evidence is `DECLARED`; external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Local contracts, parsers, typed IR, planners, four candidate generators, handlers, CLI, checkpoints and fail-closed tests are implemented. They do not prove an official-toolchain build, emulator/device journey, visual or behavior equivalence, upload, review, payment, or release.
- Runtime dispatch is owned by `engines/frontend-client-engine`: `npm run miniapp` (`dist/src/miniapp-cli.js`), structured handler `handleMiniappSkillRequest`, JSON handler `runMiniappSkillJson`, full flow `runMiniappConversion`, strict package flow `runMiniappPackageConversion`, and single-Skill handler `executeMiniappSkill` with Skill key `miniapp-component-mapping-engine`.
- The canonical snake_case request at `skills/elmos-frontend-to-miniapp-skills-v1.0.0/schemas/conversion-request.schema.json` is callable as `npm run miniapp -- package`; handler action `run-package` receives `packageInput` and invokes `validateMiniappPackageConversionInput` then `compileMiniappPackageConversionInput` without disk discovery or package-script execution.
- Component analysis/emission is an explicit downstream adapter at `engines/component-dialect-engine`: `npm run miniapp-worker` (`dist/miniapp-worker.js`), `handleMiniAppWorkerRequest` / `runMiniAppWorkerJson`, emitter `emitPlatformMiniApp`.
- Every route remains directional and exact to source framework/runtime/providers and target MiniApp platform/toolchain/API versions. A reverse MiniApp-to-frontend route is separate and is not implied.
- Transform through typed UI Interaction/MiniApp Semantic IR with source traces. Regex, screenshot, WebView, full-page Canvas, silent feature drops, weakened tests, or widened permissions cannot establish equivalence.
- Real source and target builds, browser/emulator/device journeys, negative and independent holdout corpora, accessibility, privacy, permission, visual, business, and rollback evidence remain required.
- Platform credentials are references only. Upload, review, payment, refund, release, and other side effects require separate authorization and auditable idempotency controls.
- Only the conservative Batch 32 client gate may raise readiness; static package validation cannot certify this Skill.
