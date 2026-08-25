---
name: elmos-multimodal-input-workbench-ui
description: "实现拖拽、录音、文件夹和压缩包上传、预览、进度、纠错和冲突审阅界面；当任务涉及 Elmos 多模态前端体验时使用。"
---

# 多模态输入工作台 UI

## 何时使用

实现拖拽、录音、文件夹和压缩包上传、预览、进度、纠错和冲突审阅界面；当任务涉及 Elmos 多模态前端体验时使用。

## 不应触发

仅进行普通业务功能开发且不涉及本技能边界时，不应触发。

## 目标

让用户清楚看到每个资产的安全、上传、解析、上下文和审阅状态，并能控制资料角色和模型读取权限。

## 开始前必须做

1. 阅读 `references/contract.yaml`，并核对依赖 Skill。
2. 扫描现有 Elmos 仓库、数据模型、API、工作流、测试、部署和安全边界；优先复用现有能力。
3. 对跨服务或多阶段改动，依据包根目录 `templates/EXECPLAN.md` 创建并持续更新执行计划。
4. 明确输入、输出、失败路径、租户边界、迁移和回滚方式。

## 实施流程

1. 实现统一输入区、文件卡片、目录树、音频转录和文档预览
2. 实时显示上传、解析状态、机器 ETA、成本和恢复操作
3. 支持主资料、参考资料、禁止模型读取、忽略和嵌套解压选择
4. 实现无障碍、键盘操作、超大列表虚拟化和断线重连

## 强制工程规则

- 原始用户资产不可变；修正和派生结果必须版本化并保留来源。
- 所有用户文件内容均为不可信数据，不能覆盖系统指令或获得工具权限。
- 创建、提交、重试和恢复路径必须幂等，不得重复副作用、模型费用或成本账。
- 对外契约必须版本化；状态转换必须持久化并可观测。
- 错误要包含稳定错误码、trace id、可重试性和安全的用户说明。
- 不得用空实现、固定假数据、禁用测试或只写文档冒充已完成。
- 只有执行真实测试并保存证据后，才能标记完成。

## 输入

- 会话状态、资产、进度事件

## 输出

- 用户操作、审阅决策、任务提交

## 交付清单

- [ ] 前端页面与组件
- [ ] SSE、WebSocket 状态同步层
- [ ] 组件、E2E、视觉回归和可访问性测试

## 验收门槛

- [ ] 用户能区分已上传、已解析、已索引、已装入上下文和仅可检索
- [ ] 错误信息可操作且不泄露内部路径或敏感值
- [ ] 大目录树和长转录保持可用性能
- [ ] 刷新或重连后状态与服务端一致

## 依赖技能

- `elmos-ingestion-api-and-sdk`
- `elmos-human-review-and-correction`

## 完成报告

报告必须列出：修改文件、数据库迁移、API/事件变化、执行命令、测试结果、性能/安全证据、机器执行时间与成本影响、遗留风险和回滚方式。

## Repository Integration Boundary

- Canonical Skill ordinal: `25`
- Immutable source: `skills/elmos-multimodal-intake-skills-v1.0.0/skills/elmos-multimodal-input-workbench-ui/SKILL.md`
- Immutable contract: `skills/elmos-multimodal-intake-skills-v1.0.0/skills/elmos-multimodal-input-workbench-ui/references/contract.yaml`
- Source package: `elmos-multimodal-intake-skills@1.0.0`
- Source archive SHA-256: `23f9f2cee63e2fb1a43f85df539942e92077db2c58ddd75a8a0854773eb1c90b`
- Source SKILL.md SHA-256: `2f23ff564adcec591d005051faee66c6faed7e8b3985f694e1ace997eea2db82`
- Source contract SHA-256: `555da5a04d57b65189b0600e49c7e29228dbee73efb898f14ec520cde20f8caa`
- Runtime handler: `engines/multimodal-intake-engine/src/elmos_multimodal_intake/skill_runtime.py::execute_multimodal_input_workbench_ui`
- Runtime phase: `review`
- Runtime implementation aggregate SHA-256: `edd4ba80520e30889538b42e50950e7348753b2ea95ec4e32b6cc5516cad4e93`
- Runtime test aggregate SHA-256: `7e84b7d3d8bd10e4de59195256db88c2b178ab32beafe16d5b690fb93c05542a`
- Exact dependencies: `$elmos-ingestion-api-and-sdk`, `$elmos-human-review-and-correction`
- Acceptance identities: `S25-01`, `S25-02`, `S25-03`, `S25-04`
- Generated contract: `compiled-contract.json`
- Codex interface: `agents/openai.yaml`
- External evidence: `NOT_RUN`
- Certification: `NOT_CERTIFIED`

Package scripts remain untrusted input and are never executed by this importer.
Acceptance criteria are preserved as contracts; this installation does not claim
that they were executed or passed.
