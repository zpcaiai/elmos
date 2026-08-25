---
name: miniapp-differential-testing
description: Capture and compare source and target behavior traces for routes, state,
  events, network contracts, storage, errors, and key user flows across all generated
  miniapps. Use to prove semantic parity and drive repair.
license: Proprietary
metadata:
  package: elmos.frontend-to-miniapp.skills
  version: 1.0.0
  stage: validation
  task_ids:
  - MAPP-031
  - MAPP-032
  maturity: implementation-ready
---

# miniapp-differential-testing

## 目标

通过相同场景和可控依赖比较源应用与目标小程序行为，而不是只看是否能编译。

## 何时使用

- 目标工程可运行
- 关键流程或状态行为需要验收
- 自动修复需要可重复失败证据

## 输入

- source runnable harness or recorded traces
- target builds
- test-plan.json
- normalizers

输入必须来自固定的仓库修订或带内容哈希的任务产物。发现缺失字段时，先输出结构化阻断项；不要凭空补齐平台权限、业务规则或凭证。

## 输出

- differential-result.json
- flow-traces/**
- semantic-diff-report.html
- repair-candidates.json

所有 JSON 输出必须通过本包 `schemas/` 中对应的 Draft 2020-12 Schema；所有生成文件必须进入 artifact index，并记录源修订、规则版本与内容哈希。

## 依赖技能

- wechat-miniapp-codegen
- alipay-miniapp-codegen
- douyin-miniapp-codegen
- xiaohongshu-miniapp-codegen

## 执行流程

1. 为关键流程定义初始状态、输入、模拟网络、时间、随机数和预期观察点。
2. 在源与目标运行相同场景，捕获路由、状态、事件、请求、存储和错误。
3. 对平台无关字段做受控归一化，不掩盖业务差异。
4. 比较顺序、值、次数、错误语义和副作用。
5. 将差异定位到 source trace、IR 节点、生成规则和目标文件。
6. 按 severity、determinism、blast radius 生成修复候选。
7. 对不稳定测试执行隔离与重放，不把 flaky 当通过。

## 强制规则

- 关键流程不得仅以截图判定
- 归一化规则必须版本化
- 网络和支付测试默认使用 mock/sandbox

通用规则：

- 不得声称“转换完成”而没有编译、测试和证据。
- 不得在客户端代码、日志、报告或 fixture 中写入真实平台密钥。
- 不得静默删除功能、事件、权限、数据流或错误处理。
- 生成步骤必须确定性；同一输入和规则版本应产生相同规范化输出。
- 外部工具链、账户权限、平台审核或真实支付不可用时，输出 `blocked` 及证据，不得伪造成功。
- 任何有副作用的动作必须有幂等键、审批状态和回滚/补偿策略。

## 验收门禁

- 关键流程 100% 通过
- 无未分类差异
- 失败可重复或明确标记 flaky 并阻断

## 常见失败与升级条件

- 源应用不可运行
- 测试依赖外部实时数据
- 非确定性动画/时间
- 平台行为本质不同

遇到以下任一条件必须停止自动执行并升级到 orchestrator：需要真实支付/退款/发布、需要扩大权限、需要降低安全或质量门禁、连续两次产生等价补丁、达到最大修复次数、或无法证明行为等价。

## 任务追踪

- 任务 ID：MAPP-031, MAPP-032
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

- Source identity is pinned to `elmos.frontend-to-miniapp.skills` `1.0.0`, Skill `miniapp-differential-testing`, and `sha256:c56a932cee5c6665b9c090acf7274c3aa1a51982d6fa516b5ed8af13c9e1f5e0`.
- The source label `implementation-ready` describes package intent only. The repository handler bytes are present but no valid local qualification receipt exists, so runtime evidence is `DECLARED`; external evidence remains `NOT_RUN` and certification remains `NOT_CERTIFIED`.
- Local contracts, parsers, typed IR, planners, four candidate generators, handlers, CLI, checkpoints and fail-closed tests are implemented. They do not prove an official-toolchain build, emulator/device journey, visual or behavior equivalence, upload, review, payment, or release.
- Runtime dispatch is owned by `engines/frontend-client-engine`: `npm run miniapp` (`dist/src/miniapp-cli.js`), structured handler `handleMiniappSkillRequest`, JSON handler `runMiniappSkillJson`, full flow `runMiniappConversion`, strict package flow `runMiniappPackageConversion`, and single-Skill handler `executeMiniappSkill` with Skill key `miniapp-differential-testing`.
- The canonical snake_case request at `skills/elmos-frontend-to-miniapp-skills-v1.0.0/schemas/conversion-request.schema.json` is callable as `npm run miniapp -- package`; handler action `run-package` receives `packageInput` and invokes `validateMiniappPackageConversionInput` then `compileMiniappPackageConversionInput` without disk discovery or package-script execution.
- Component analysis/emission is an explicit downstream adapter at `engines/component-dialect-engine`: `npm run miniapp-worker` (`dist/miniapp-worker.js`), `handleMiniAppWorkerRequest` / `runMiniAppWorkerJson`, emitter `emitPlatformMiniApp`.
- Every route remains directional and exact to source framework/runtime/providers and target MiniApp platform/toolchain/API versions. A reverse MiniApp-to-frontend route is separate and is not implied.
- Transform through typed UI Interaction/MiniApp Semantic IR with source traces. Regex, screenshot, WebView, full-page Canvas, silent feature drops, weakened tests, or widened permissions cannot establish equivalence.
- Real source and target builds, browser/emulator/device journeys, negative and independent holdout corpora, accessibility, privacy, permission, visual, business, and rollback evidence remain required.
- Platform credentials are references only. Upload, review, payment, refund, release, and other side effects require separate authorization and auditable idempotency controls.
- Only the conservative Batch 32 client gate may raise readiness; static package validation cannot certify this Skill.
