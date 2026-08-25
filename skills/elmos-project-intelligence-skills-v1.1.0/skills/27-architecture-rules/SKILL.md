---
name: elmos-architecture-rules
description: 定义并执行分层、依赖、安全、数据、接口和部署架构规则。用于阻止循环依赖、越界访问、共享数据库和未鉴权接口。
license: Proprietary-Elmos
compatibility: Agent Skills open format; compatible with OpenAI Codex/ChatGPT Skills
  and Claude Code. Requires repository read access; write or execution only when the
  task needs it.
metadata:
  version: 1.1.0
  category: intelligence
  title_zh: 架构规则与策略引擎
  batch: BATCH-07-search-impact-governance-analysis
  owner: elmos-project-intelligence
---

# 架构规则与策略引擎

## 目标

将架构原则转为可版本化、可测试、可豁免、可在 CI 执行的规则。

## 使用边界

- 当请求与本技能描述直接匹配时使用。
- 跨多个能力域、批次或需要长任务编排时，先调用 `elmos-insight-orchestrator`。
- 只实现本技能负责的完整垂直切片；不要把接口桩、TODO 或设计稿标记为完成。
- 读取 `references/module-spec.md` 后再修改代码。

## 输入

- Intelligence Graph
- Rule DSL
- scope/revision
- waivers

## 必须输出

- violations
- rule coverage
- CI status
- fix recommendations

## 执行流程

1. 定义 Rule DSL：scope、selector、condition、severity、evidence、exceptions。
2. 实现内建规则与项目自定义规则。
3. 在全量和增量图谱上执行规则。
4. 为 violation 生成最短证据路径和修复建议。
5. 支持 waiver、到期时间、owner 和审批。
6. 集成 PR check、dashboard 和架构文档。

## 实施要求

- 内建规则覆盖分层、循环、服务调用、数据库归属、认证、敏感数据、依赖许可证。
- 规则版本与分析 run 绑定。
- 允许 dry-run 和历史回放。
- 规则性能需有预算。
- 修复建议与自动修改分离。

## 安全与可信度约束

- 不得因 waiver 隐藏原始 violation。
- 规则失败不能被解释为通过。
- 自动修复前必须有补丁和验证。

## 依赖技能

- `elmos-project-intelligence-graph`

## 预期交付物

- `architecture-rules.yaml`
- `rule-engine-report.json`

## 完成定义

- [ ] 规则 DSL 有 Schema 和单元测试。
- [ ] 已知违规被稳定检测。
- [ ] 例外到期后恢复失败。
- [ ] CI 输出可定位到代码和路径。
- [ ] 增量结果与全量结果一致。

## 验证

1. 执行本模块单元、契约、集成、E2E、安全或性能测试。
2. 将需求、实现文件、测试和证据写入追踪矩阵。
3. 运行仓库级验证命令；本技能包自身使用：

```bash
python3 scripts/validate_skillpack.py
```

4. 输出 `system_wall_clock_eta_p50/p90` 与 `human_review_effort` 时必须分列。
5. 对未完成项、低置信度推断和外部依赖明确标注，禁止用“已完成”掩盖。
