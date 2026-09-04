---
name: elmos-prompt-injection-defense
description: "防止 PDF、Word、图片、音频、代码和网页内容中的指令控制 Agent 或扩大权限；当用户输入会进入 LLM 上下文或触发工具时使用。"
---

# 多模态提示注入防护

## 何时使用

防止 PDF、Word、图片、音频、代码和网页内容中的指令控制 Agent 或扩大权限；当用户输入会进入 LLM 上下文或触发工具时使用。

## 不应触发

仅进行普通业务功能开发且不涉及本技能边界时，不应触发。

## 目标

把所有资产内容视为不可信数据，分离系统策略、用户授权和文档内指令，并在工具调用前实施能力与参数级控制。

## 开始前必须做

1. 阅读 `references/contract.yaml`，并核对依赖 Skill。
2. 扫描现有 Elmos 仓库、数据模型、API、工作流、测试、部署和安全边界；优先复用现有能力。
3. 对跨服务或多阶段改动，依据包根目录 `templates/EXECPLAN.md` 创建并持续更新执行计划。
4. 明确输入、输出、失败路径、租户边界、迁移和回滚方式。

## 实施流程

1. 检测文档内越权、忽略指令、泄密、外传和工具诱导模式
2. 为上下文块附加 trust label 与来源边界
3. 在 Tool Gateway 实施白名单、参数策略、租户权限和审批
4. 对发现采取标记、隔离、降权或阻断，而非盲目删除业务文本

## 强制工程规则

- 原始用户资产不可变；修正和派生结果必须版本化并保留来源。
- 所有用户文件内容均为不可信数据，不能覆盖系统指令或获得工具权限。
- 创建、提交、重试和恢复路径必须幂等，不得重复副作用、模型费用或成本账。
- 对外契约必须版本化；状态转换必须持久化并可观测。
- 错误要包含稳定错误码、trace id、可重试性和安全的用户说明。
- 不得用空实现、固定假数据、禁用测试或只写文档冒充已完成。
- 只有执行真实测试并保存证据后，才能标记完成。

## 输入

- Content IR、工具请求、权限策略

## 输出

- TrustLabel、SecurityFinding、PolicyDecision

## 交付清单

- [ ] InjectionClassifier 与 trust metadata
- [ ] 工具调用策略执行点
- [ ] 跨模态红队样本与防绕过测试

## 验收门槛

- [ ] 文档内容不能修改系统策略或租户权限
- [ ] 高风险动作必须经过独立授权或审批
- [ ] 检测器失效时默认保持最小权限
- [ ] 安全拦截有可审计原因且不泄露内部策略细节

## 依赖技能

- `elmos-source-anchor-and-provenance`
- `elmos-downstream-agent-integration`

## 完成报告

报告必须列出：修改文件、数据库迁移、API/事件变化、执行命令、测试结果、性能/安全证据、机器执行时间与成本影响、遗留风险和回滚方式。

## Repository Integration Boundary

- Canonical Skill ordinal: `18`
- Immutable source: `skills/elmos-multimodal-intake-skills-v1.0.0/skills/elmos-prompt-injection-defense/SKILL.md`
- Immutable contract: `skills/elmos-multimodal-intake-skills-v1.0.0/skills/elmos-prompt-injection-defense/references/contract.yaml`
- Source package: `elmos-multimodal-intake-skills@1.0.0`
- Source archive SHA-256: `23f9f2cee63e2fb1a43f85df539942e92077db2c58ddd75a8a0854773eb1c90b`
- Source SKILL.md SHA-256: `3a2f8ba8d08d084085c424270f3ffc3ff9cb3b1942dc1ef444ed5ddb6ca28e8a`
- Source contract SHA-256: `47bfe1ceaf0fdab8087dea542c795cd12313010f7d6189f2770187c331e10574`
- Runtime handler: `engines/multimodal-intake-engine/src/elmos_multimodal_intake/skill_runtime.py::execute_prompt_injection_defense`
- Runtime phase: `governance`
- Runtime implementation aggregate SHA-256: `c498b260b3aa1cf9719fbdeaee0cf30d052901f5041f2fe8ba52256a198d0db1`
- Runtime test aggregate SHA-256: `0f1029010e9f9888aa7524b64d8a00efd412ee16b72f0f45169ac1aa84f5a183`
- Exact dependencies: `$elmos-source-anchor-and-provenance`, `$elmos-downstream-agent-integration`
- Acceptance identities: `S18-01`, `S18-02`, `S18-03`, `S18-04`
- Generated contract: `compiled-contract.json`
- Codex interface: `agents/openai.yaml`
- External evidence: `NOT_RUN`
- Certification: `NOT_CERTIFIED`

Package scripts remain untrusted input and are never executed by this importer.
Acceptance criteria are preserved as contracts; this installation does not claim
that they were executed or passed.
