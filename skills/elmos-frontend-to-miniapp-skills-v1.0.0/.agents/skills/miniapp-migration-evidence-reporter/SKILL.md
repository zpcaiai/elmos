---
name: miniapp-migration-evidence-reporter
description: Assemble an auditable evidence graph linking source revisions, IR nodes,
  mapping decisions, generated files, builds, tests, repairs, approvals, costs, and
  release status. Use at every checkpoint and for final migration sign-off.
license: Proprietary
metadata:
  package: elmos.frontend-to-miniapp.skills
  version: 1.0.0
  stage: evidence
  task_ids:
  - MAPP-039
  - MAPP-040
  maturity: implementation-ready
---

# miniapp-migration-evidence-reporter

## 目标

让“已完成转换”成为可验证结论，而不是代理的主观声明。

## 何时使用

- 阶段完成或任务中断
- 需要生成兼容性、测试、风险或上线报告
- 需要核算任务成本和追溯决策

## 输入

- all run artifacts
- gate results
- task ledger
- approval records
- cost records

输入必须来自固定的仓库修订或带内容哈希的任务产物。发现缺失字段时，先输出结构化阻断项；不要凭空补齐平台权限、业务规则或凭证。

## 输出

- migration-evidence.json
- compatibility-report.html
- validation-report.md
- release-readiness.md
- artifact-index.json

所有 JSON 输出必须通过本包 `schemas/` 中对应的 Draft 2020-12 Schema；所有生成文件必须进入 artifact index，并记录源修订、规则版本与内容哈希。

## 依赖技能

- miniapp-ci-build-release
- miniapp-differential-testing
- miniapp-visual-regression-testing
- miniapp-privacy-permission-auditor

## 执行流程

1. 索引源版本、请求、IR、平台计划、生成文件和所有测试产物。
2. 验证每个 claim 都有证据 URI、哈希、时间和生产者。
3. 汇总 A-E 兼容分类、未决风险、阻断项和人工决策。
4. 记录自动修复迭代、补丁、回滚点和复测结果。
5. 记录任务运行时、模型/工具调用成本、平台构建成本和状态。
6. 按 acceptance gates 生成 ready/not-ready，不允许缺证据时标 ready。
7. 输出机器可读 JSON 与人类可读报告，并支持恢复任务重放。

## 强制规则

- 不得把计划或未运行测试写成已通过
- 证据哈希必须与文件一致
- 未知状态必须显示 unknown

通用规则：

- 不得声称“转换完成”而没有编译、测试和证据。
- 不得在客户端代码、日志、报告或 fixture 中写入真实平台密钥。
- 不得静默删除功能、事件、权限、数据流或错误处理。
- 生成步骤必须确定性；同一输入和规则版本应产生相同规范化输出。
- 外部工具链、账户权限、平台审核或真实支付不可用时，输出 `blocked` 及证据，不得伪造成功。
- 任何有副作用的动作必须有幂等键、审批状态和回滚/补偿策略。

## 验收门禁

- 所有关键 claim 有证据
- 产物索引无悬空引用
- 最终结论与门禁一致
- 成本与运行状态可追溯

## 常见失败与升级条件

- 日志或产物丢失
- 哈希不一致
- 测试结果过期
- 审批记录缺失

遇到以下任一条件必须停止自动执行并升级到 orchestrator：需要真实支付/退款/发布、需要扩大权限、需要降低安全或质量门禁、连续两次产生等价补丁、达到最大修复次数、或无法证明行为等价。

## 任务追踪

- 任务 ID：MAPP-039, MAPP-040
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
