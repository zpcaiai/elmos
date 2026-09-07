---
name: douyin-miniapp-codegen
description: Generate a native Douyin Mini Program project from validated IR and plans,
  including app/page configuration, components, styles, JS APIs, server OpenAPI contracts,
  tests, toolchain metadata, and traceability. Use only for the Douyin target.
license: Proprietary
metadata:
  package: elmos.frontend-to-miniapp.skills
  version: 1.0.0
  stage: target-codegen
  task_ids:
  - MAPP-025
  maturity: implementation-ready
---

# douyin-miniapp-codegen

## 目标

生成抖音原生小程序工程，并显式处理内容、视频、直播、电商和场景入口能力。

## 何时使用

- conversion targets 包含 douyin
- 修复抖音目标构建或场景差异

## 输入

- validated IR
- mapping/lifecycle/style/dependency plans
- Douyin platform profile

输入必须来自固定的仓库修订或带内容哈希的任务产物。发现缺失字段时，先输出结构化阻断项；不要凭空补齐平台权限、业务规则或凭证。

## 输出

- platforms/douyin/**
- douyin-codegen-report.json
- douyin-trace-map.json

所有 JSON 输出必须通过本包 `schemas/` 中对应的 Draft 2020-12 Schema；所有生成文件必须进入 artifact index，并记录源修订、规则版本与内容哈希。

## 依赖技能

- miniapp-component-mapping-engine
- miniapp-state-event-lifecycle-converter
- miniapp-style-layout-converter
- miniapp-third-party-dependency-migrator

## 执行流程

1. 生成应用配置、页面、组件、样式、脚本和资源。
2. 按抖音事件、生命周期、场景值和入口参数建立绑定。
3. 将 JS API 与服务端 OpenAPI 分离，服务端能力只生成接口 contract。
4. 适配登录、分享、内容、媒体、直播、电商等经注册表确认的能力。
5. 生成开发者工具构建、预览和上传元数据。
6. 生成场景入口、弱网、重复提交和媒体权限测试。
7. 输出平台差异、权限条件和 trace。

## 强制规则

- 客户端不得持有服务端 secret
- 内容/直播/电商能力必须检查资质与类目
- 不以普通 H5 替代原生页面

通用规则：

- 不得声称“转换完成”而没有编译、测试和证据。
- 不得在客户端代码、日志、报告或 fixture 中写入真实平台密钥。
- 不得静默删除功能、事件、权限、数据流或错误处理。
- 生成步骤必须确定性；同一输入和规则版本应产生相同规范化输出。
- 外部工具链、账户权限、平台审核或真实支付不可用时，输出 `blocked` 及证据，不得伪造成功。
- 任何有副作用的动作必须有幂等键、审批状态和回滚/补偿策略。

## 验收门禁

- 官方工具链构建通过
- 场景值测试通过
- 关键媒体/内容能力有契约证据

## 常见失败与升级条件

- 类目或资质不足
- OpenAPI 权限缺失
- 媒体行为不一致
- 场景入口未覆盖

遇到以下任一条件必须停止自动执行并升级到 orchestrator：需要真实支付/退款/发布、需要扩大权限、需要降低安全或质量门禁、连续两次产生等价补丁、达到最大修复次数、或无法证明行为等价。

## 任务追踪

- 任务 ID：MAPP-025
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
