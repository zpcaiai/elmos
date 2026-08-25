---
name: miniapp-third-party-dependency-migrator
description: Classify every frontend dependency and choose retain, replace, rewrite,
  backend-move, isolate, or remove-with-approval actions for each target miniapp.
  Use before generation; never drop a package merely because it lacks a direct equivalent.
license: Proprietary
metadata:
  package: elmos.frontend-to-miniapp.skills
  version: 1.0.0
  stage: planning
  task_ids:
  - MAPP-021
  - MAPP-022
  maturity: implementation-ready
---

# miniapp-third-party-dependency-migrator

## 目标

将 NPM、Dart package、原生插件和平台 SDK 转为可审计的替代图和实施任务。

## 何时使用

- 依赖清单已生成
- 构建失败来自第三方库
- 需要评估 UI、状态、网络、媒体或原生插件

## 输入

- dependency inventory
- source usage graph
- target platform profiles
- license/security policy

输入必须来自固定的仓库修订或带内容哈希的任务产物。发现缺失字段时，先输出结构化阻断项；不要凭空补齐平台权限、业务规则或凭证。

## 输出

- dependency-migration-plan.json
- replacement-graph.json
- license-report.json
- supply-chain-findings.json

所有 JSON 输出必须通过本包 `schemas/` 中对应的 Draft 2020-12 Schema；所有生成文件必须进入 artifact index，并记录源修订、规则版本与内容哈希。

## 依赖技能

- miniapp-source-framework-detector
- miniapp-capability-registry

## 执行流程

1. 区分实际使用、传递依赖、开发依赖和未使用依赖。
2. 分析依赖 API 使用面，而不是仅比较包名。
3. 按平台选择保留、替代、重写、后端迁移、隔离或经批准移除。
4. 检查许可证、维护状态、漏洞、包体积和运行时限制。
5. 为 Flutter 原生插件和浏览器专属包生成能力级替代。
6. 定义适配层接口，避免业务代码直接依赖四个平台 SDK。
7. 为每个决策生成风险、工作项、回滚和测试。

## 强制规则

- 删除必须有明确批准和功能影响
- 替代库必须满足行为与许可证要求
- 禁止把服务端密钥依赖迁入前端

通用规则：

- 不得声称“转换完成”而没有编译、测试和证据。
- 不得在客户端代码、日志、报告或 fixture 中写入真实平台密钥。
- 不得静默删除功能、事件、权限、数据流或错误处理。
- 生成步骤必须确定性；同一输入和规则版本应产生相同规范化输出。
- 外部工具链、账户权限、平台审核或真实支付不可用时，输出 `blocked` 及证据，不得伪造成功。
- 任何有副作用的动作必须有幂等键、审批状态和回滚/补偿策略。

## 验收门禁

- 所有直接依赖有决策
- 实际调用面可追踪
- 高风险供应链项已阻断或批准

## 常见失败与升级条件

- 闭源插件
- 无维护替代
- 许可证冲突
- 动态加载依赖

遇到以下任一条件必须停止自动执行并升级到 orchestrator：需要真实支付/退款/发布、需要扩大权限、需要降低安全或质量门禁、连续两次产生等价补丁、达到最大修复次数、或无法证明行为等价。

## 任务追踪

- 任务 ID：MAPP-021, MAPP-022
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
