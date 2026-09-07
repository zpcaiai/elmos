---
name: elmos-release-certification
description: 汇总功能、质量、性能、安全、恢复、证据和运营结果，执行 Elmos Project Intelligence Studio 或项目转换输出的分级生产认证。
license: Proprietary-Elmos
compatibility: Agent Skills open format; compatible with OpenAI Codex/ChatGPT Skills
  and Claude Code. Requires repository read access; write or execution only when the
  task needs it.
metadata:
  version: 1.1.0
  category: quality
  title_zh: 生产验收与 E1–E5 认证
  batch: BATCH-12-deployment-and-certification
  owner: elmos-project-intelligence
---

# 生产验收与 E1–E5 认证

## 目标

用证据驱动的门禁决定是否可试用、可团队使用、可生产或可关键业务部署。

## 使用边界

- 当请求与本技能描述直接匹配时使用。
- 跨多个能力域、批次或需要长任务编排时，先调用 `elmos-insight-orchestrator`。
- 只实现本技能负责的完整垂直切片；不要把接口桩、TODO 或设计稿标记为完成。
- 读取 `references/module-spec.md` 后再修改代码。

## 输入

- release candidate
- quality gates
- SLO/security/recovery evidence
- waivers

## 必须输出

- certification matrix
- pass/fail
- residual risks
- signed evidence bundle

## 执行流程

1. 定义 E1 原型、E2 可验证、E3 团队级、E4 生产级、E5 关键业务级标准。
2. 收集构建、测试、评测、性能、安全、权限、恢复和文档证据。
3. 验证证据新鲜度、revision、环境和完整性。
4. 执行硬门禁与可审批 waiver。
5. 生成失败项、修复任务、残余风险和重新认证范围。
6. 冻结并签名认证报告。

## 实施要求

- 严重安全、数据隔离、恢复和证据缺失为硬门禁。
- 认证标准版本化。
- 每项标准关联自动测试或人工审批。
- 不同部署模式可有附加控制但不能降低核心安全。
- 认证结果在 UI、报告和 API 一致。

## 安全与可信度约束

- 不得由生成该结果的同一主体单独认证 E4/E5。
- 不得用过期或不同 revision 证据。
- 不得把 waiver 隐藏在附件。

## 依赖技能

- `elmos-testing-evaluation`
- `elmos-security-threat-model`
- `elmos-deployment-private-cloud`

## 预期交付物

- `certification-matrix.yaml`
- `certification-report.md`
- `signed-evidence-bundle.zip`

## 完成定义

- [ ] 所有门禁有明确证据。
- [ ] 失败可生成可执行修复 backlog。
- [ ] 签名包可离线验证。
- [ ] 认证状态变更有职责分离与审计。
- [ ] E4/E5 通过灾备和安全红队。

## 验证

1. 执行本模块单元、契约、集成、E2E、安全或性能测试。
2. 将需求、实现文件、测试和证据写入追踪矩阵。
3. 运行仓库级验证命令；本技能包自身使用：

```bash
python3 scripts/validate_skillpack.py
```

4. 输出 `system_wall_clock_eta_p50/p90` 与 `human_review_effort` 时必须分列。
5. 对未完成项、低置信度推断和外部依赖明确标注，禁止用“已完成”掩盖。
