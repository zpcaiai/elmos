---
name: xiaohongshu-miniapp-codegen
description: Generate a native Xiaohongshu Mini Program project from validated IR
  and plans, including pages, components, styles, authorization, commerce/content
  adapters, tests, third-party platform metadata, and traceability. Use only for the
  Xiaohongshu target.
license: Proprietary
metadata:
  package: elmos.frontend-to-miniapp.skills
  version: 1.0.0
  stage: target-codegen
  task_ids:
  - MAPP-026
  maturity: implementation-ready
---

# xiaohongshu-miniapp-codegen

## 目标

生成小红书原生工程，并处理专业号、授权、内容、商品和支付模式的条件依赖。

## 何时使用

- conversion targets 包含 xiaohongshu
- 修复小红书目标构建、授权或交易差异

## 输入

- validated IR
- mapping/lifecycle/style/dependency plans
- Xiaohongshu platform profile

输入必须来自固定的仓库修订或带内容哈希的任务产物。发现缺失字段时，先输出结构化阻断项；不要凭空补齐平台权限、业务规则或凭证。

## 输出

- platforms/xiaohongshu/**
- xiaohongshu-codegen-report.json
- xiaohongshu-trace-map.json

所有 JSON 输出必须通过本包 `schemas/` 中对应的 Draft 2020-12 Schema；所有生成文件必须进入 artifact index，并记录源修订、规则版本与内容哈希。

## 依赖技能

- miniapp-component-mapping-engine
- miniapp-state-event-lifecycle-converter
- miniapp-style-layout-converter
- miniapp-third-party-dependency-migrator

## 执行流程

1. 生成小红书项目结构、页面、组件、样式和配置。
2. 通过 adapter 接入授权、内容、商品、订单、分享和平台入口。
3. 对服务商代开发、多租户授权和 token 轮换仅生成服务端 contract。
4. 按能力注册表选择支付与订单模式，禁止假定统一平台原生支付。
5. 生成开发工具构建、场景、授权回调和交易契约测试。
6. 输出资质、专业号、类目和审核依赖。
7. 生成 trace 与平台专项兼容报告。

## 强制规则

- 不得把微信/支付宝交易流程直接复制
- 授权票据和 refresh token 不得进入客户端
- 平台能力未知时归 D

通用规则：

- 不得声称“转换完成”而没有编译、测试和证据。
- 不得在客户端代码、日志、报告或 fixture 中写入真实平台密钥。
- 不得静默删除功能、事件、权限、数据流或错误处理。
- 生成步骤必须确定性；同一输入和规则版本应产生相同规范化输出。
- 外部工具链、账户权限、平台审核或真实支付不可用时，输出 `blocked` 及证据，不得伪造成功。
- 任何有副作用的动作必须有幂等键、审批状态和回滚/补偿策略。

## 验收门禁

- 官方工具链构建通过或有可验证阻断证据
- 授权/交易 contract 完整
- 资质依赖已披露

## 常见失败与升级条件

- 开放能力变化
- 专业号或类目限制
- 第三方授权配置缺失
- 支付链路无等价方案

遇到以下任一条件必须停止自动执行并升级到 orchestrator：需要真实支付/退款/发布、需要扩大权限、需要降低安全或质量门禁、连续两次产生等价补丁、达到最大修复次数、或无法证明行为等价。

## 任务追踪

- 任务 ID：MAPP-026
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

- Source identity is pinned to `elmos.frontend-to-miniapp.skills` `1.0.0`, Skill `xiaohongshu-miniapp-codegen`, and `sha256:5e513cab823540490e82ffe80273bff686b368111fbda099a483d8bb9f0a3044`.
- The source label `implementation-ready` describes package intent only. The repository handler bytes are present but no valid local qualification receipt exists, so runtime evidence is `DECLARED`; external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Local contracts, parsers, typed IR, planners, four candidate generators, handlers, CLI, checkpoints and fail-closed tests are implemented. They do not prove an official-toolchain build, emulator/device journey, visual or behavior equivalence, upload, review, payment, or release.
- Runtime dispatch is owned by `engines/frontend-client-engine`: `npm run miniapp` (`dist/src/miniapp-cli.js`), structured handler `handleMiniappSkillRequest`, JSON handler `runMiniappSkillJson`, full flow `runMiniappConversion`, strict package flow `runMiniappPackageConversion`, and single-Skill handler `executeMiniappSkill` with Skill key `xiaohongshu-miniapp-codegen`.
- The canonical snake_case request at `skills/elmos-frontend-to-miniapp-skills-v1.0.0/schemas/conversion-request.schema.json` is callable as `npm run miniapp -- package`; handler action `run-package` receives `packageInput` and invokes `validateMiniappPackageConversionInput` then `compileMiniappPackageConversionInput` without disk discovery or package-script execution.
- Component analysis/emission is an explicit downstream adapter at `engines/component-dialect-engine`: `npm run miniapp-worker` (`dist/miniapp-worker.js`), `handleMiniAppWorkerRequest` / `runMiniAppWorkerJson`, emitter `emitPlatformMiniApp`.
- Every route remains directional and exact to source framework/runtime/providers and target MiniApp platform/toolchain/API versions. A reverse MiniApp-to-frontend route is separate and is not implied.
- Transform through typed UI Interaction/MiniApp Semantic IR with source traces. Regex, screenshot, WebView, full-page Canvas, silent feature drops, weakened tests, or widened permissions cannot establish equivalence.
- Real source and target builds, browser/emulator/device journeys, negative and independent holdout corpora, accessibility, privacy, permission, visual, business, and rollback evidence remain required.
- Platform credentials are references only. Upload, review, payment, refund, release, and other side effects require separate authorization and auditable idempotency controls.
- Only the conservative Batch 32 client gate may raise readiness; static package validation cannot certify this Skill.
