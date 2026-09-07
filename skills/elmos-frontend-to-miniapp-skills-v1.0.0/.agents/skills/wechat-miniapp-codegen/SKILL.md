---
name: wechat-miniapp-codegen
description: Generate a native WeChat Mini Program project from validated IR and plans,
  including pages, components, styles, app configuration, subpackages, platform APIs,
  tests, and build metadata. Use only for the WeChat target.
license: Proprietary
metadata:
  package: elmos.frontend-to-miniapp.skills
  version: 1.0.0
  stage: target-codegen
  task_ids:
  - MAPP-023
  maturity: implementation-ready
---

# wechat-miniapp-codegen

## 目标

生成可由微信官方工具链编译、预览和上传的原生目标工程，并保持完整 trace。

## 何时使用

- conversion targets 包含 wechat
- 修复微信目标构建或行为差异

## 输入

- validated IR
- mapping/lifecycle/style/dependency plans
- WeChat platform profile

输入必须来自固定的仓库修订或带内容哈希的任务产物。发现缺失字段时，先输出结构化阻断项；不要凭空补齐平台权限、业务规则或凭证。

## 输出

- platforms/wechat/**
- wechat-codegen-report.json
- wechat-trace-map.json

所有 JSON 输出必须通过本包 `schemas/` 中对应的 Draft 2020-12 Schema；所有生成文件必须进入 artifact index，并记录源修订、规则版本与内容哈希。

## 依赖技能

- miniapp-component-mapping-engine
- miniapp-state-event-lifecycle-converter
- miniapp-style-layout-converter
- miniapp-third-party-dependency-migrator

## 执行流程

1. 按确定性顺序生成 app、page、component、style 和配置文件。
2. 生成路由、分包、Tab、资源和环境配置，不写入任何真实密钥。
3. 通过平台适配层接入登录、支付、分享、存储、网络、媒体等能力。
4. 对共享业务代码使用稳定 contract；平台条件逻辑保持在 adapter 内。
5. 生成单元、组件、契约和端到端测试入口。
6. 运行格式化、静态检查和项目结构验证。
7. 输出每个目标文件对应的 IR 节点和生成规则版本。

## 强制规则

- 不得生成 WebView 壳作为默认结果
- AppSecret 不得进入客户端
- 平台 API 调用必须经过可替换适配器

通用规则：

- 不得声称“转换完成”而没有编译、测试和证据。
- 不得在客户端代码、日志、报告或 fixture 中写入真实平台密钥。
- 不得静默删除功能、事件、权限、数据流或错误处理。
- 生成步骤必须确定性；同一输入和规则版本应产生相同规范化输出。
- 外部工具链、账户权限、平台审核或真实支付不可用时，输出 `blocked` 及证据，不得伪造成功。
- 任何有副作用的动作必须有幂等键、审批状态和回滚/补偿策略。

## 验收门禁

- 目标结构完整
- 静态检查通过
- 官方构建通过
- 关键能力契约通过

## 常见失败与升级条件

- 平台 API 无权限
- 包体积超限
- 配置冲突
- 官方工具链失败

遇到以下任一条件必须停止自动执行并升级到 orchestrator：需要真实支付/退款/发布、需要扩大权限、需要降低安全或质量门禁、连续两次产生等价补丁、达到最大修复次数、或无法证明行为等价。

## 任务追踪

- 任务 ID：MAPP-023
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
