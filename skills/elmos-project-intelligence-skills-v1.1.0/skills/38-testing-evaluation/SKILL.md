---
name: elmos-testing-evaluation
description: 设计单元、契约、集成、E2E、性能、安全、故障恢复和 AI 质量评测。用于验证解析、图谱、解释、图表、文档和问答是否可信。
license: Proprietary-Elmos
compatibility: Agent Skills open format; compatible with OpenAI Codex/ChatGPT Skills
  and Claude Code. Requires repository read access; write or execution only when the
  task needs it.
metadata:
  version: 1.1.0
  category: quality
  title_zh: 测试、评测与数据质量
  batch: BATCH-11-testing-conversion-estimation
  owner: elmos-project-intelligence
---

# 测试、评测与数据质量

## 目标

建立可重复的黄金仓库、故障注入、视觉快照和生产门禁。

## 使用边界

- 当请求与本技能描述直接匹配时使用。
- 跨多个能力域、批次或需要长任务编排时，先调用 `elmos-insight-orchestrator`。
- 只实现本技能负责的完整垂直切片；不要把接口桩、TODO 或设计稿标记为完成。
- 读取 `references/module-spec.md` 后再修改代码。

## 输入

- requirements
- language matrix
- golden repositories
- risk model

## 必须输出

- test strategy
- fixtures
- eval datasets
- quality gates
- reports

## 执行流程

1. 建立小型合成仓库和真实许可基准仓库。
2. 为 parser、graph、evidence、rule、merge、renderer 写单元/属性测试。
3. 为 API/Event/DB/connector 写契约测试。
4. 为核心用户旅程写浏览器 E2E。
5. 建立问答、讲解、流程发现、图表和文档的黄金评测。
6. 运行性能、安全、恢复、权限和数据质量门禁。

## 实施要求

- 指标覆盖 precision、recall、citation correctness、abstention、stability。
- 视觉测试优先比较结构与关键布局，不只像素。
- 随机抽样人工评审结果可回流。
- 每个严重缺陷必须加入回归 fixture。
- 测试报告绑定 commit 和环境。

## 安全与可信度约束

- 不得使用含私密客户代码的公开评测集。
- 不得只验证文件生成成功而不验证内容。
- 模型升级必须重新跑关键评测。

## 依赖技能

- `elmos-product-scope`
- `elmos-evidence-provenance`

## 预期交付物

- `test-strategy.md`
- `evals/`
- `quality-gates.yaml`

## 完成定义

- [ ] 所有 P0 Story 有自动化验收。
- [ ] 黄金集版本化。
- [ ] 权限、注入、恢复和幂等场景通过。
- [ ] 质量回退能阻止发布。
- [ ] 测试失败可定位到需求和技能。

## 验证

1. 执行本模块单元、契约、集成、E2E、安全或性能测试。
2. 将需求、实现文件、测试和证据写入追踪矩阵。
3. 运行仓库级验证命令；本技能包自身使用：

```bash
python3 scripts/validate_skillpack.py
```

4. 输出 `system_wall_clock_eta_p50/p90` 与 `human_review_effort` 时必须分列。
5. 对未完成项、低置信度推断和外部依赖明确标注，禁止用“已完成”掩盖。
