---
name: miniapp-privacy-permission-auditor
description: Audit generated miniapps for permissions, personal-data flows, secrets,
  logging, storage, consent, third-party SDKs, and platform review disclosures. Use
  before release and after any capability or dependency change.
license: Proprietary
metadata:
  package: elmos.frontend-to-miniapp.skills
  version: 1.0.0
  stage: validation
  task_ids:
  - MAPP-029
  - MAPP-030
  maturity: implementation-ready
---

# miniapp-privacy-permission-auditor

## 目标

建立从 UI 触发到平台 API、网络、存储和服务端的数据流证据，阻断密钥和隐私违规。

## 何时使用

- 代码生成完成
- 新增登录、位置、相机、相册、手机号、支付等能力
- 准备上传或提交审核

## 输入

- generated projects
- IR privacy nodes
- capability resolution
- dependency plan

输入必须来自固定的仓库修订或带内容哈希的任务产物。发现缺失字段时，先输出结构化阻断项；不要凭空补齐平台权限、业务规则或凭证。

## 输出

- privacy-report.json
- permission-manifest.json
- secret-scan.json
- review-disclosure-checklist.md

所有 JSON 输出必须通过本包 `schemas/` 中对应的 Draft 2020-12 Schema；所有生成文件必须进入 artifact index，并记录源修订、规则版本与内容哈希。

## 依赖技能

- miniapp-capability-registry
- miniapp-third-party-dependency-migrator
- wechat-miniapp-codegen
- alipay-miniapp-codegen
- douyin-miniapp-codegen
- xiaohongshu-miniapp-codegen

## 执行流程

1. 扫描明文 secret、私钥、token、调试账号、内部 URL 和敏感日志。
2. 构建个人数据从触发、采集、传输、存储、共享到删除的数据流。
3. 对平台权限调用检查用途说明、触发时机、最小权限和失败降级。
4. 识别第三方 SDK 的数据采集、域名、存储和授权要求。
5. 检查本地存储、缓存、日志、崩溃上报和分析事件中的敏感字段。
6. 生成平台审核披露与隐私政策所需事实，不替代法律审核。
7. 高风险发现阻断构建或发布；修复后必须重新扫描。

## 强制规则

- 扫描结果不得包含真实 secret 全文
- 权限必须按需触发
- 无法证明用途的敏感权限默认阻断

通用规则：

- 不得声称“转换完成”而没有编译、测试和证据。
- 不得在客户端代码、日志、报告或 fixture 中写入真实平台密钥。
- 不得静默删除功能、事件、权限、数据流或错误处理。
- 生成步骤必须确定性；同一输入和规则版本应产生相同规范化输出。
- 外部工具链、账户权限、平台审核或真实支付不可用时，输出 `blocked` 及证据，不得伪造成功。
- 任何有副作用的动作必须有幂等键、审批状态和回滚/补偿策略。

## 验收门禁

- 严重/高危 secret=0
- 敏感数据流 100% 可追踪
- 权限与声明一致
- 第三方 SDK 已披露

## 常见失败与升级条件

- 混淆代码不可审计
- 动态 SDK 注入
- 隐私政策缺失
- 平台规则未知

遇到以下任一条件必须停止自动执行并升级到 orchestrator：需要真实支付/退款/发布、需要扩大权限、需要降低安全或质量门禁、连续两次产生等价补丁、达到最大修复次数、或无法证明行为等价。

## 任务追踪

- 任务 ID：MAPP-029, MAPP-030
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
