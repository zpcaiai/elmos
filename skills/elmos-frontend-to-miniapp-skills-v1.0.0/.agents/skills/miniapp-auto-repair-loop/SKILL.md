---
name: miniapp-auto-repair-loop
description: Apply bounded, evidence-driven repairs to IR, mappings, adapters, or
  generated code, then rerun the smallest valid test set and all affected gates. Use
  only when a reproducible finding and rollback point exist.
license: Proprietary
metadata:
  package: elmos.frontend-to-miniapp.skills
  version: 1.0.0
  stage: repair
  task_ids:
  - MAPP-035
  - MAPP-036
  maturity: implementation-ready
---

# miniapp-auto-repair-loop

## 目标

自动修复可定位的问题，同时防止无限循环、扩大改动和绕过验收门禁。

## 何时使用

- 构建、差分、视觉、隐私或性能测试产生可重现 finding
- 用户要求自动修改并复测

## 输入

- repair candidates
- current revision
- test evidence
- repair policy

输入必须来自固定的仓库修订或带内容哈希的任务产物。发现缺失字段时，先输出结构化阻断项；不要凭空补齐平台权限、业务规则或凭证。

## 输出

- repair-action.json
- patches/**
- repair-history.json
- post-repair-validation.json

所有 JSON 输出必须通过本包 `schemas/` 中对应的 Draft 2020-12 Schema；所有生成文件必须进入 artifact index，并记录源修订、规则版本与内容哈希。

## 依赖技能

- miniapp-differential-testing
- miniapp-visual-regression-testing
- miniapp-privacy-permission-auditor

## 执行流程

1. 验证 finding 可重现并定位到规则、IR、adapter 或生成文件。
2. 优先修复上游规则或 IR，避免直接手改大量生成代码。
3. 生成最小补丁、影响面、回滚点和预期测试。
4. 静态验证补丁并运行最小失败测试。
5. 运行受影响的完整门禁，确认无回归。
6. 比较补丁指纹，禁止重复应用相同或等价无效修复。
7. 达到最大迭代、风险阈值或需要凭证/业务决策时停止并升级。

## 强制规则

- 默认最多 3 次自动迭代
- 安全/支付/隐私策略不得通过降低门禁修复
- 生成文件修复应回写生成规则

通用规则：

- 不得声称“转换完成”而没有编译、测试和证据。
- 不得在客户端代码、日志、报告或 fixture 中写入真实平台密钥。
- 不得静默删除功能、事件、权限、数据流或错误处理。
- 生成步骤必须确定性；同一输入和规则版本应产生相同规范化输出。
- 外部工具链、账户权限、平台审核或真实支付不可用时，输出 `blocked` 及证据，不得伪造成功。
- 任何有副作用的动作必须有幂等键、审批状态和回滚/补偿策略。

## 验收门禁

- 失败已消失
- 受影响门禁全部通过
- 无新高严重度 finding
- 补丁可回滚

## 常见失败与升级条件

- 问题不可重现
- 修复需要业务决策
- 重复补丁
- 影响面过大

遇到以下任一条件必须停止自动执行并升级到 orchestrator：需要真实支付/退款/发布、需要扩大权限、需要降低安全或质量门禁、连续两次产生等价补丁、达到最大修复次数、或无法证明行为等价。

## 任务追踪

- 任务 ID：MAPP-035, MAPP-036
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
