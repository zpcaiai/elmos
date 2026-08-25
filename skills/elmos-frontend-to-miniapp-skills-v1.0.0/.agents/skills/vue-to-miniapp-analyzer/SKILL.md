---
name: vue-to-miniapp-analyzer
description: Analyze Vue 2/3 projects, including SFCs, Options API, Composition API,
  script setup, Vue Router, Vuex, Pinia, slots, directives, and styles, and emit source
  semantic facts for MiniApp IR. Use only after repository inventory.
license: Proprietary
metadata:
  package: elmos.frontend-to-miniapp.skills
  version: 1.0.0
  stage: source-analysis
  task_ids:
  - MAPP-005
  - MAPP-006
  maturity: implementation-ready
---

# vue-to-miniapp-analyzer

## 目标

把 Vue 语法、响应式状态和运行时行为还原为与目标平台无关的语义事实。

## 何时使用

- 检测到 Vue SFC、Vue Router、Vuex 或 Pinia
- 需要定位 Vue 特性为何无法转换

## 输入

- project-inventory.json
- Vue 源文件与 tsconfig/build 配置
- 源依赖图

输入必须来自固定的仓库修订或带内容哈希的任务产物。发现缺失字段时，先输出结构化阻断项；不要凭空补齐平台权限、业务规则或凭证。

## 输出

- vue-analysis.json
- component-graph.json
- route-graph.json
- state-graph.json
- source-trace-map.json

所有 JSON 输出必须通过本包 `schemas/` 中对应的 Draft 2020-12 Schema；所有生成文件必须进入 artifact index，并记录源修订、规则版本与内容哈希。

## 依赖技能

- miniapp-source-framework-detector

## 执行流程

1. 使用 SFC/TypeScript AST 分别解析 template、script、style，保留源位置。
2. 归一化 Vue 2 Options API、Vue 3 Composition API 与 script setup。
3. 展开 v-if、v-for、v-model、slot、provide/inject、动态组件和自定义指令语义。
4. 解析 props、emits、refs、computed、watch、生命周期与副作用。
5. 提取 Vue Router 路由、守卫、懒加载和参数约束。
6. 提取 Vuex/Pinia 模块、action、getter、持久化和跨组件依赖。
7. 标记依赖真实 DOM、Teleport、浏览器插件、SSR 或不可静态求值的代码。

## 强制规则

- 不得以正则替代 AST 作为主分析方法
- 不得把 computed/watch 简化为普通字段而丢失依赖
- 所有不确定语义必须带源位置和置信度

通用规则：

- 不得声称“转换完成”而没有编译、测试和证据。
- 不得在客户端代码、日志、报告或 fixture 中写入真实平台密钥。
- 不得静默删除功能、事件、权限、数据流或错误处理。
- 生成步骤必须确定性；同一输入和规则版本应产生相同规范化输出。
- 外部工具链、账户权限、平台审核或真实支付不可用时，输出 `blocked` 及证据，不得伪造成功。
- 任何有副作用的动作必须有幂等键、审批状态和回滚/补偿策略。

## 验收门禁

- 所有 SFC 均有解析结果或错误记录
- 路由与 store 引用闭合
- 源节点到 IR 候选的 trace 覆盖率=100%

## 常见失败与升级条件

- 宏或编译插件未识别
- 动态 import 路径不可解析
- 运行时模板
- 重度 DOM 操作

遇到以下任一条件必须停止自动执行并升级到 orchestrator：需要真实支付/退款/发布、需要扩大权限、需要降低安全或质量门禁、连续两次产生等价补丁、达到最大修复次数、或无法证明行为等价。

## 任务追踪

- 任务 ID：MAPP-005, MAPP-006
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
