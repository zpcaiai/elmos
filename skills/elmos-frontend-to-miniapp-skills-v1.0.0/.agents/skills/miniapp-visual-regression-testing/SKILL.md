---
name: miniapp-visual-regression-testing
description: Run deterministic screenshot, layout, typography, safe-area, responsive,
  theme, and interaction-state comparisons between source and target pages. Use after
  semantic tests; visual similarity never overrides functional failures.
license: Proprietary
metadata:
  package: elmos.frontend-to-miniapp.skills
  version: 1.0.0
  stage: validation
  task_ids:
  - MAPP-033
  - MAPP-034
  maturity: implementation-ready
---

# miniapp-visual-regression-testing

## 目标

以可解释的像素与结构差分发现布局、字体、资源和交互状态偏差。

## 何时使用

- 目标页面可渲染
- 样式或组件映射发生变化
- 需要达到视觉相似度门禁

## 输入

- source baselines
- target builds
- viewport/device matrix
- mask/normalization rules

输入必须来自固定的仓库修订或带内容哈希的任务产物。发现缺失字段时，先输出结构化阻断项；不要凭空补齐平台权限、业务规则或凭证。

## 输出

- visual-diff-report.html
- screenshots/**
- layout-diffs.json
- visual-repair-candidates.json

所有 JSON 输出必须通过本包 `schemas/` 中对应的 Draft 2020-12 Schema；所有生成文件必须进入 artifact index，并记录源修订、规则版本与内容哈希。

## 依赖技能

- miniapp-style-layout-converter
- miniapp-differential-testing

## 执行流程

1. 固定数据、时间、语言、主题、字体、网络和动画状态。
2. 在定义的设备与页面状态矩阵中捕获源和目标截图。
3. 计算像素、结构框、文本换行、溢出、安全区和交互状态差异。
4. 对动态内容只使用显式 mask，不得扩大遮罩掩盖真实问题。
5. 将差异关联到 style/component mapping 和目标文件。
6. 按关键区域加权并生成最小作用域修复建议。
7. 重跑语义测试，防止视觉修复破坏行为。

## 强制规则

- 功能失败时视觉通过无效
- mask 必须审计
- 默认阈值 0.95 可由页面级策略提高但不得无理由降低

通用规则：

- 不得声称“转换完成”而没有编译、测试和证据。
- 不得在客户端代码、日志、报告或 fixture 中写入真实平台密钥。
- 不得静默删除功能、事件、权限、数据流或错误处理。
- 生成步骤必须确定性；同一输入和规则版本应产生相同规范化输出。
- 外部工具链、账户权限、平台审核或真实支付不可用时，输出 `blocked` 及证据，不得伪造成功。
- 任何有副作用的动作必须有幂等键、审批状态和回滚/补偿策略。

## 验收门禁

- 确定性页面相似度达到请求阈值
- 关键区域无严重差异
- 无文本截断或不可操作控件

## 常见失败与升级条件

- 字体不可用
- 动态内容不稳定
- 官方模拟器截图不可自动化
- 平台原生控件视觉差异

遇到以下任一条件必须停止自动执行并升级到 orchestrator：需要真实支付/退款/发布、需要扩大权限、需要降低安全或质量门禁、连续两次产生等价补丁、达到最大修复次数、或无法证明行为等价。

## 任务追踪

- 任务 ID：MAPP-033, MAPP-034
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
