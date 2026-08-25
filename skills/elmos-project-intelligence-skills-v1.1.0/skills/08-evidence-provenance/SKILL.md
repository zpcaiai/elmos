---
name: elmos-evidence-provenance
description: 为项目结论、图节点、文档段落和 PPT 页面建立证据、可信度、来源和可重放记录。用于防止幻觉和支持审计。
license: Proprietary-Elmos
compatibility: Agent Skills open format; compatible with OpenAI Codex/ChatGPT Skills
  and Claude Code. Requires repository read access; write or execution only when the
  task needs it.
metadata:
  version: 1.1.0
  category: analysis-core
  title_zh: 证据图、可信度与来源追踪
  batch: BATCH-02-graphs-and-evidence
  owner: elmos-project-intelligence
---

# 证据图、可信度与来源追踪

## 目标

让每个事实都可验证，明确区分 Confirmed、Inferred、Unknown 和 Recommended。

## 使用边界

- 当请求与本技能描述直接匹配时使用。
- 跨多个能力域、批次或需要长任务编排时，先调用 `elmos-insight-orchestrator`。
- 只实现本技能负责的完整垂直切片；不要把接口桩、TODO 或设计稿标记为完成。
- 读取 `references/module-spec.md` 后再修改代码。

## 输入

- 代码位置
- 配置/Schema
- 测试结果
- Trace/日志
- 模型推断

## 必须输出

- Evidence Graph
- Claim records
- confidence score
- provenance links

## 执行流程

1. 定义 Evidence、Claim、Inference、Recommendation 数据模型。
2. 为文件行、AST、配置键、Trace span、测试结果生成稳定引用。
3. 按规则计算证据强度、冲突和新鲜度。
4. 将 claim 绑定到 artifact block、diagram node 和 slide element。
5. 发现冲突时降级置信度并生成待确认任务。
6. 提供点击回源和批量证据导出。

## 实施要求

- 可信度模型必须可解释、可配置。
- 运行时证据有时间范围和环境标签。
- 文档引用在代码变更后自动标记 stale。
- 敏感证据需脱敏和权限检查。
- 推断必须记录使用的规则/模型/提示版本。

## 安全与可信度约束

- 不得将模型自述作为事实证据。
- 不得引用已删除 revision 的行号而不标记 stale。
- 低权限用户不能通过证据链接绕过文件权限。

## 依赖技能

- `elmos-multilanguage-parsing`

## 预期交付物

- `evidence-bundle.json`
- `claim-register.json`

## 完成定义

- [ ] 随机抽取 claim 能定位到有效证据。
- [ ] 代码移动后可通过 symbol/revision 重定位或明确失效。
- [ ] 冲突证据不被静默选择。
- [ ] 导出的证据包可离线验证哈希。
- [ ] 所有生成器强制写 claim/evidence 关系。

## 验证

1. 执行本模块单元、契约、集成、E2E、安全或性能测试。
2. 将需求、实现文件、测试和证据写入追踪矩阵。
3. 运行仓库级验证命令；本技能包自身使用：

```bash
python3 scripts/validate_skillpack.py
```

4. 输出 `system_wall_clock_eta_p50/p90` 与 `human_review_effort` 时必须分列。
5. 对未完成项、低置信度推断和外部依赖明确标注，禁止用“已完成”掩盖。
