---
name: miniapp-semantic-ir
description: Define, validate, version, serialize, and migrate the shared MiniApp
  Semantic IR for components, routes, state, lifecycle, events, styles, capabilities,
  assets, privacy, and traceability. Use whenever source facts or target code cross
  adapter boundaries.
license: Proprietary
metadata:
  package: elmos.frontend-to-miniapp.skills
  version: 1.0.0
  stage: ir
  task_ids:
  - MAPP-011
  - MAPP-012
  maturity: implementation-ready
---

# miniapp-semantic-ir

## 目标

建立稳定的中间表示，隔离源框架与四个目标平台，支持规则复用、差分验证和增量转换。

## 何时使用

- 新增或修改 IR 节点
- 源适配器输出需要归一化
- 目标代码生成器需要读取语义模型

## 输入

- source analysis artifacts
- semantic-ir.schema.json
- IR 版本与迁移规则

输入必须来自固定的仓库修订或带内容哈希的任务产物。发现缺失字段时，先输出结构化阻断项；不要凭空补齐平台权限、业务规则或凭证。

## 输出

- semantic-ir.json
- ir-validation.json
- ir-trace-index.json
- ir-migration-log.json

所有 JSON 输出必须通过本包 `schemas/` 中对应的 Draft 2020-12 Schema；所有生成文件必须进入 artifact index，并记录源修订、规则版本与内容哈希。

## 依赖技能

- vue-to-miniapp-analyzer
- react-to-miniapp-analyzer
- flutter-widget-semantic-reconstructor

## 执行流程

1. 按 schema_version 创建 Application、Route、Component、State、Event、Style、Capability、Asset 和 Trace 节点。
2. 为每个节点分配稳定 ID、源位置、置信度和内容哈希。
3. 把框架专属语法下降为语义操作，不提前编码目标平台细节。
4. 验证引用完整性、类型约束、循环依赖、生命周期顺序和能力引用。
5. 对 IR 版本变化提供向前迁移脚本，不允许隐式破坏性升级。
6. 生成可供差分测试使用的行为观察点和可供代码生成使用的确定性排序。
7. 保存源节点→IR→目标文件的双向 trace。

## 强制规则

- IR 必须确定性序列化
- 未知字段保留或显式拒绝，禁止静默丢弃
- 目标平台特性通过 capability/extension 节点表达

通用规则：

- 不得声称“转换完成”而没有编译、测试和证据。
- 不得在客户端代码、日志、报告或 fixture 中写入真实平台密钥。
- 不得静默删除功能、事件、权限、数据流或错误处理。
- 生成步骤必须确定性；同一输入和规则版本应产生相同规范化输出。
- 外部工具链、账户权限、平台审核或真实支付不可用时，输出 `blocked` 及证据，不得伪造成功。
- 任何有副作用的动作必须有幂等键、审批状态和回滚/补偿策略。

## 验收门禁

- Draft 2020-12 Schema 通过
- 引用闭合
- 序列化稳定
- trace 覆盖率=100%

## 常见失败与升级条件

- Schema 版本不兼容
- 语义冲突
- 循环引用
- 缺少源 trace

遇到以下任一条件必须停止自动执行并升级到 orchestrator：需要真实支付/退款/发布、需要扩大权限、需要降低安全或质量门禁、连续两次产生等价补丁、达到最大修复次数、或无法证明行为等价。

## 任务追踪

- 任务 ID：MAPP-011, MAPP-012
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

- Source identity is pinned to `elmos.frontend-to-miniapp.skills` `1.0.0`, Skill `miniapp-semantic-ir`, and `sha256:9f54bf171c5c8e7906fdb60352b7f04c46d93c22d6fbf55bdb3b2cd2cbec7196`.
- The source label `implementation-ready` describes package intent only. The repository handler bytes are present but no valid local qualification receipt exists, so runtime evidence is `DECLARED`; external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Local contracts, parsers, typed IR, planners, four candidate generators, handlers, CLI, checkpoints and fail-closed tests are implemented. They do not prove an official-toolchain build, emulator/device journey, visual or behavior equivalence, upload, review, payment, or release.
- Runtime dispatch is owned by `engines/frontend-client-engine`: `npm run miniapp` (`dist/src/miniapp-cli.js`), structured handler `handleMiniappSkillRequest`, JSON handler `runMiniappSkillJson`, full flow `runMiniappConversion`, strict package flow `runMiniappPackageConversion`, and single-Skill handler `executeMiniappSkill` with Skill key `miniapp-semantic-ir`.
- The canonical snake_case request at `skills/elmos-frontend-to-miniapp-skills-v1.0.0/schemas/conversion-request.schema.json` is callable as `npm run miniapp -- package`; handler action `run-package` receives `packageInput` and invokes `validateMiniappPackageConversionInput` then `compileMiniappPackageConversionInput` without disk discovery or package-script execution.
- Component analysis/emission is an explicit downstream adapter at `engines/component-dialect-engine`: `npm run miniapp-worker` (`dist/miniapp-worker.js`), `handleMiniAppWorkerRequest` / `runMiniAppWorkerJson`, emitter `emitPlatformMiniApp`.
- Every route remains directional and exact to source framework/runtime/providers and target MiniApp platform/toolchain/API versions. A reverse MiniApp-to-frontend route is separate and is not implied.
- Transform through typed UI Interaction/MiniApp Semantic IR with source traces. Regex, screenshot, WebView, full-page Canvas, silent feature drops, weakened tests, or widened permissions cannot establish equivalence.
- Real source and target builds, browser/emulator/device journeys, negative and independent holdout corpora, accessibility, privacy, permission, visual, business, and rollback evidence remain required.
- Platform credentials are references only. Upload, review, payment, refund, release, and other side effects require separate authorization and auditable idempotency controls.
- Only the conservative Batch 32 client gate may raise readiness; static package validation cannot certify this Skill.
