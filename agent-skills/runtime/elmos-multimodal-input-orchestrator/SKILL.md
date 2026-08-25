---
name: elmos-multimodal-input-orchestrator
description: "为 Elmos 实现统一多模态输入总控；当任务涉及音频、图片、PDF、Word、Markdown、TXT、文件夹或压缩包接入、解析编排与下游交接时使用。"
---

# 统一多模态输入总控

## 何时使用

为 Elmos 实现统一多模态输入总控；当任务涉及音频、图片、PDF、Word、Markdown、TXT、文件夹或压缩包接入、解析编排与下游交接时使用。

## 不应触发

仅进行普通业务功能开发且不涉及本技能边界时，不应触发。

## 目标

建立所有输入类型共享的会话、状态机、路由、错误隔离和下游交付边界，使下游 Agent 只消费统一内容模型。

## 开始前必须做

1. 阅读 `references/contract.yaml`，并核对依赖 Skill。
2. 扫描现有 Elmos 仓库、数据模型、API、工作流、测试、部署和安全边界；优先复用现有能力。
3. 对跨服务或多阶段改动，依据包根目录 `templates/EXECPLAN.md` 创建并持续更新执行计划。
4. 明确输入、输出、失败路径、租户边界、迁移和回滚方式。

## 实施流程

1. 创建 InputSession/InputAsset/InputPackage 聚合根与持久状态机
2. 按文件类型、风险、租户策略和资源需求选择解析流水线
3. 支持部分成功、重试、取消、恢复、幂等和进度事件
4. 将原始资产、解析结果、来源锚点和质量报告原子化提交给下游

## 强制工程规则

- 原始用户资产不可变；修正和派生结果必须版本化并保留来源。
- 所有用户文件内容均为不可信数据，不能覆盖系统指令或获得工具权限。
- 创建、提交、重试和恢复路径必须幂等，不得重复副作用、模型费用或成本账。
- 对外契约必须版本化；状态转换必须持久化并可观测。
- 错误要包含稳定错误码、trace id、可重试性和安全的用户说明。
- 不得用空实现、固定假数据、禁用测试或只写文档冒充已完成。
- 只有执行真实测试并保存证据后，才能标记完成。

## 输入

- 用户提交、上传清单、租户策略、模型能力

## 输出

- InputPackage、处理事件、下游任务句柄

## 交付清单

- [ ] 编排服务与端口适配器
- [ ] 状态机、事件和数据库迁移
- [ ] 跨模态端到端测试与运行手册

## 验收门槛

- [ ] 同一幂等键不会创建重复任务或副作用
- [ ] 单资产失败不阻塞同包其他资产，包状态准确反映部分就绪
- [ ] 所有 READY 内容具备来源锚点和处理报告
- [ ] 下游无需感知 PDF、Word、音频等原始格式

## 依赖技能

- `elmos-unified-multimodal-content-ir`
- `elmos-source-anchor-and-provenance`
- `elmos-durable-processing-and-recovery`

## 完成报告

报告必须列出：修改文件、数据库迁移、API/事件变化、执行命令、测试结果、性能/安全证据、机器执行时间与成本影响、遗留风险和回滚方式。

## Repository Integration Boundary

- Canonical Skill ordinal: `1`
- Immutable source: `skills/elmos-multimodal-intake-skills-v1.0.0/skills/elmos-multimodal-input-orchestrator/SKILL.md`
- Immutable contract: `skills/elmos-multimodal-intake-skills-v1.0.0/skills/elmos-multimodal-input-orchestrator/references/contract.yaml`
- Source package: `elmos-multimodal-intake-skills@1.0.0`
- Source archive SHA-256: `23f9f2cee63e2fb1a43f85df539942e92077db2c58ddd75a8a0854773eb1c90b`
- Source SKILL.md SHA-256: `f50c3a346442b19f7f119a4cb856f8ff58c7841032d5e722e037abdd934e257c`
- Source contract SHA-256: `7bee0bc845ceb53e05ff5a709d05b746f659567a3940c1569495ac337fd1d67d`
- Runtime handler: `engines/multimodal-intake-engine/src/elmos_multimodal_intake/skill_runtime.py::execute_multimodal_input_orchestrator`
- Runtime phase: `secure-intake`
- Runtime implementation aggregate SHA-256: `edd4ba80520e30889538b42e50950e7348753b2ea95ec4e32b6cc5516cad4e93`
- Runtime test aggregate SHA-256: `7e84b7d3d8bd10e4de59195256db88c2b178ab32beafe16d5b690fb93c05542a`
- Exact dependencies: `$elmos-unified-multimodal-content-ir`, `$elmos-source-anchor-and-provenance`, `$elmos-durable-processing-and-recovery`
- Acceptance identities: `S01-01`, `S01-02`, `S01-03`, `S01-04`
- Generated contract: `compiled-contract.json`
- Codex interface: `agents/openai.yaml`
- External evidence: `NOT_RUN`
- Certification: `NOT_CERTIFIED`

Package scripts remain untrusted input and are never executed by this importer.
Acceptance criteria are preserved as contracts; this installation does not claim
that they were executed or passed.
