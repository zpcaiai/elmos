---
name: miniapp-source-framework-detector
description: Inventory a frontend repository and detect Vue, React, Flutter, H5, Taro,
  uni-app, or native miniapp frameworks with evidence and confidence. Use before conversion
  planning; do not infer a single framework from filenames alone.
license: Proprietary
metadata:
  package: elmos.frontend-to-miniapp.skills
  version: 1.0.0
  stage: discovery
  task_ids:
  - MAPP-003
  - MAPP-004
  maturity: implementation-ready
---

# miniapp-source-framework-detector

## 目标

建立完整、可追溯的源项目清单，识别单体、多包、微前端和混合框架边界。

## 何时使用

- 首次接收前端仓库
- 源框架、版本或入口不明确
- 转换失败后怀疑漏扫模块或平台 API

## 输入

- 只读源仓库
- include/exclude glob
- 可选 framework_hint

输入必须来自固定的仓库修订或带内容哈希的任务产物。发现缺失字段时，先输出结构化阻断项；不要凭空补齐平台权限、业务规则或凭证。

## 输出

- project-inventory.json
- framework-detection.json
- entrypoint-map.json
- unresolved-signals.json

所有 JSON 输出必须通过本包 `schemas/` 中对应的 Draft 2020-12 Schema；所有生成文件必须进入 artifact index，并记录源修订、规则版本与内容哈希。

## 依赖技能

- 无；可作为入口或独立发现技能执行

## 执行流程

1. 固定仓库提交、子模块和锁文件摘要。
2. 扫描包管理器、构建配置、扩展名、导入图、路由入口、平台配置和生成代码标记。
3. 区分应用、共享包、组件库、原生插件、服务端代码和测试代码。
4. 识别 Vue/React 混用、Flutter module、Taro/uni-app、多小程序目标等复合形态。
5. 为每个框架候选输出证据、版本范围、置信度和冲突信号。
6. 提取组件、路由、状态库、样式体系、资源、浏览器 API 与第三方依赖的初步清单。
7. 对被忽略目录、二进制文件、代码生成目录和无法解析文件给出覆盖率报告。

## 强制规则

- 不得执行不可信仓库脚本
- 默认不读取 .env 的值，只记录键名与位置
- 置信度低于 0.8 时不得自动锁定单一框架

通用规则：

- 不得声称“转换完成”而没有编译、测试和证据。
- 不得在客户端代码、日志、报告或 fixture 中写入真实平台密钥。
- 不得静默删除功能、事件、权限、数据流或错误处理。
- 生成步骤必须确定性；同一输入和规则版本应产生相同规范化输出。
- 外部工具链、账户权限、平台审核或真实支付不可用时，输出 `blocked` 及证据，不得伪造成功。
- 任何有副作用的动作必须有幂等键、审批状态和回滚/补偿策略。

## 验收门禁

- 扫描文件覆盖率=100%（排除项有理由）
- 入口与路由根可追踪
- 锁文件和依赖清单已记录

## 常见失败与升级条件

- 巨型单文件或损坏归档
- 动态生成配置
- 缺失锁文件
- 多框架冲突

遇到以下任一条件必须停止自动执行并升级到 orchestrator：需要真实支付/退款/发布、需要扩大权限、需要降低安全或质量门禁、连续两次产生等价补丁、达到最大修复次数、或无法证明行为等价。

## 任务追踪

- 任务 ID：MAPP-003, MAPP-004
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

- Source identity is pinned to `elmos.frontend-to-miniapp.skills` `1.0.0`, Skill `miniapp-source-framework-detector`, and `sha256:6e7b1a07d81ab6f7c20f1c719903e1f7a1e65c8af4e70541a06449d78acd2bfc`.
- The source label `implementation-ready` describes package intent only. The repository handler bytes are present but no valid local qualification receipt exists, so runtime evidence is `DECLARED`; external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Local contracts, parsers, typed IR, planners, four candidate generators, handlers, CLI, checkpoints and fail-closed tests are implemented. They do not prove an official-toolchain build, emulator/device journey, visual or behavior equivalence, upload, review, payment, or release.
- Runtime dispatch is owned by `engines/frontend-client-engine`: `npm run miniapp` (`dist/src/miniapp-cli.js`), structured handler `handleMiniappSkillRequest`, JSON handler `runMiniappSkillJson`, full flow `runMiniappConversion`, strict package flow `runMiniappPackageConversion`, and single-Skill handler `executeMiniappSkill` with Skill key `miniapp-source-framework-detector`.
- The canonical snake_case request at `skills/elmos-frontend-to-miniapp-skills-v1.0.0/schemas/conversion-request.schema.json` is callable as `npm run miniapp -- package`; handler action `run-package` receives `packageInput` and invokes `validateMiniappPackageConversionInput` then `compileMiniappPackageConversionInput` without disk discovery or package-script execution.
- Component analysis/emission is an explicit downstream adapter at `engines/component-dialect-engine`: `npm run miniapp-worker` (`dist/miniapp-worker.js`), `handleMiniAppWorkerRequest` / `runMiniAppWorkerJson`, emitter `emitPlatformMiniApp`.
- Every route remains directional and exact to source framework/runtime/providers and target MiniApp platform/toolchain/API versions. A reverse MiniApp-to-frontend route is separate and is not implied.
- Transform through typed UI Interaction/MiniApp Semantic IR with source traces. Regex, screenshot, WebView, full-page Canvas, silent feature drops, weakened tests, or widened permissions cannot establish equivalence.
- Real source and target builds, browser/emulator/device journeys, negative and independent holdout corpora, accessibility, privacy, permission, visual, business, and rollback evidence remain required.
- Platform credentials are references only. Upload, review, payment, refund, release, and other side effects require separate authorization and auditable idempotency controls.
- Only the conservative Batch 32 client gate may raise readiness; static package validation cannot certify this Skill.
