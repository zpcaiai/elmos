---
name: miniapp-state-event-lifecycle-converter
description: Lower framework state, derived values, effects, events, navigation hooks,
  and component/page/app lifecycles into platform-neutral execution plans and target-specific
  bindings. Use before code generation and during semantic diff repair.
license: Proprietary
metadata:
  package: elmos.frontend-to-miniapp.skills
  version: 1.0.0
  stage: planning
  task_ids:
  - MAPP-017
  - MAPP-018
  maturity: implementation-ready
---

# miniapp-state-event-lifecycle-converter

## 目标

确保响应式依赖、事件顺序、清理逻辑、页面栈和异步副作用在转换后保持行为等价。

## 何时使用

- Vue watch/computed、React effects、Flutter State 等需要下降
- 生命周期或事件差分失败

## 输入

- semantic-ir.json
- target lifecycle profile
- component mapping plan

输入必须来自固定的仓库修订或带内容哈希的任务产物。发现缺失字段时，先输出结构化阻断项；不要凭空补齐平台权限、业务规则或凭证。

## 输出

- state-lowering-plan.json
- event-binding-plan.json
- lifecycle-plan.json
- side-effect-ledger.json

所有 JSON 输出必须通过本包 `schemas/` 中对应的 Draft 2020-12 Schema；所有生成文件必须进入 artifact index，并记录源修订、规则版本与内容哈希。

## 依赖技能

- miniapp-semantic-ir
- miniapp-component-mapping-engine

## 执行流程

1. 构建状态读写、派生值和订阅依赖图。
2. 区分组件局部、页面、应用、会话和持久化状态。
3. 把源生命周期映射到 app/page/component 生命周期并处理缺失阶段。
4. 保持事件捕获、冒泡、阻止默认、节流、防抖和自定义事件契约。
5. 为异步请求、定时器、订阅、WebSocket、媒体和导航副作用建立创建/清理对。
6. 检测竞态、重复提交、过期响应和页面销毁后的写入。
7. 生成可观测事件与状态快照供差分测试使用。

## 强制规则

- 不得把 effect 当普通赋值
- 副作用必须可幂等或有去重键
- 销毁清理缺失时必须阻断关键流程

通用规则：

- 不得声称“转换完成”而没有编译、测试和证据。
- 不得在客户端代码、日志、报告或 fixture 中写入真实平台密钥。
- 不得静默删除功能、事件、权限、数据流或错误处理。
- 生成步骤必须确定性；同一输入和规则版本应产生相同规范化输出。
- 外部工具链、账户权限、平台审核或真实支付不可用时，输出 `blocked` 及证据，不得伪造成功。
- 任何有副作用的动作必须有幂等键、审批状态和回滚/补偿策略。

## 验收门禁

- 状态引用闭合
- 生命周期顺序验证
- 副作用均有创建与清理策略
- 关键事件顺序可测试

## 常见失败与升级条件

- 不可确定的并发时序
- 隐藏全局状态
- 平台生命周期缺口
- 事件模型不兼容

遇到以下任一条件必须停止自动执行并升级到 orchestrator：需要真实支付/退款/发布、需要扩大权限、需要降低安全或质量门禁、连续两次产生等价补丁、达到最大修复次数、或无法证明行为等价。

## 任务追踪

- 任务 ID：MAPP-017, MAPP-018
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
