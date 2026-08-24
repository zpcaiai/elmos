---
name: miniapp-style-layout-converter
description: Convert CSS, scoped styles, CSS Modules, CSS-in-JS, Tailwind-like utilities,
  Flutter constraints, themes, units, animations, and responsive layouts into platform-specific
  style plans. Use before code generation and visual repair.
license: Proprietary
metadata:
  package: elmos.frontend-to-miniapp.skills
  version: 1.0.0
  stage: planning
  task_ids:
  - MAPP-019
  - MAPP-020
  maturity: implementation-ready
---

# miniapp-style-layout-converter

## 目标

保持布局、主题和视觉层级，同时避免把浏览器或 Flutter 特性机械翻译为无效样式。

## 何时使用

- 需要生成 WXSS/ACSS/TTSS/平台样式
- 视觉差分或布局溢出
- 主题、字体或动画迁移

## 输入

- semantic-ir.json
- source style AST
- asset inventory
- target viewport/profile

输入必须来自固定的仓库修订或带内容哈希的任务产物。发现缺失字段时，先输出结构化阻断项；不要凭空补齐平台权限、业务规则或凭证。

## 输出

- style-plan.json
- token-map.json
- responsive-rules.json
- unsupported-style-report.json

所有 JSON 输出必须通过本包 `schemas/` 中对应的 Draft 2020-12 Schema；所有生成文件必须进入 artifact index，并记录源修订、规则版本与内容哈希。

## 依赖技能

- miniapp-semantic-ir
- miniapp-component-mapping-engine

## 执行流程

1. 解析级联、作用域、变量、媒体查询、伪类、动画和布局约束。
2. 归一化设计 token、颜色、间距、字体、层级和主题模式。
3. 把 Flex/Grid/定位/Flutter constraints 映射为目标平台可用布局。
4. 按策略转换 px/rem/vw/rpx 等单位，避免重复缩放。
5. 处理安全区、导航栏、底部栏、横竖屏和不同设备密度。
6. 将不支持的选择器、滤镜、混合模式和复杂动画分类并生成替代。
7. 输出视觉回归需要的稳定字体、时间和动态内容固定策略。

## 强制规则

- 禁止全局 !important 修复
- 不得把无法解析的样式静默丢弃
- 布局修复必须最小作用域

通用规则：

- 不得声称“转换完成”而没有编译、测试和证据。
- 不得在客户端代码、日志、报告或 fixture 中写入真实平台密钥。
- 不得静默删除功能、事件、权限、数据流或错误处理。
- 生成步骤必须确定性；同一输入和规则版本应产生相同规范化输出。
- 外部工具链、账户权限、平台审核或真实支付不可用时，输出 `blocked` 及证据，不得伪造成功。
- 任何有副作用的动作必须有幂等键、审批状态和回滚/补偿策略。

## 验收门禁

- 样式 AST 解析覆盖率=100% 或有错误清单
- 设计 token 可追踪
- 关键页面无未解释溢出

## 常见失败与升级条件

- 运行时 CSS-in-JS
- 复杂 Grid
- 自定义字体授权
- 滤镜/Shader 不支持

遇到以下任一条件必须停止自动执行并升级到 orchestrator：需要真实支付/退款/发布、需要扩大权限、需要降低安全或质量门禁、连续两次产生等价补丁、达到最大修复次数、或无法证明行为等价。

## 任务追踪

- 任务 ID：MAPP-019, MAPP-020
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
