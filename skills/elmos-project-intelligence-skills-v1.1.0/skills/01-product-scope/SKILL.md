---
name: elmos-product-scope
description: 细化 Elmos 在线代码阅读、架构讲解、流程梳理、图表、文档和 PPT 等需求，并冻结可实施范围。用于 PRD、Epic、用户故事、优先级和范围控制。
license: Proprietary-Elmos
compatibility: Agent Skills open format; compatible with OpenAI Codex/ChatGPT Skills
  and Claude Code. Requires repository read access; write or execution only when the
  task needs it.
metadata:
  version: 1.1.0
  category: foundation
  title_zh: 产品范围与需求基线
  batch: BATCH-00-product-and-reference-architecture
  owner: elmos-project-intelligence
---

# 产品范围与需求基线

## 目标

把模糊产品想法转化为有角色、有场景、有边界、有验收指标的生产级需求基线。

## 使用边界

- 当请求与本技能描述直接匹配时使用。
- 跨多个能力域、批次或需要长任务编排时，先调用 `elmos-insight-orchestrator`。
- 只实现本技能负责的完整垂直切片；不要把接口桩、TODO 或设计稿标记为完成。
- 读取 `references/module-spec.md` 后再修改代码。

## 输入

- 用户目标
- 目标客户/角色
- 现有 Elmos 能力
- 商业与合规约束

## 必须输出

- PRD
- 角色与旅程
- Epic/Story
- 范围内/范围外
- 可追踪验收矩阵

## 执行流程

1. 识别用户角色、核心任务和痛点。
2. 将能力拆为 Read、Explain、Explore、Flow、Diagram、Document、Present、Impact、Debug、Learn。
3. 定义每项能力的输入、输出、异常、权限和数据保留。
4. 按 P0-P3 排序并标注依赖。
5. 为每个 Story 编写可自动验证的完成条件。
6. 建立需求到技能、API、数据表和测试的追踪关系。

## 实施要求

- 覆盖个人、团队、企业私有化和 Elmos 转换场景。
- 明确静态分析与运行时分析的差异。
- 明确事实、推断、未知、建议四级可信度。
- 文档、图表与 PPT 必须支持增量更新和人工内容保护。
- 输出范围不得把完整通用 IDE 当作 P0。

## 安全与可信度约束

- 拒绝没有完成定义的“支持某功能”。
- 不要把依赖第三方服务的能力描述为内建保证。
- 所有非功能指标必须给出测量方法。

## 依赖技能

- 无；可作为起始技能。

## 预期交付物

- `docs/01-product-requirements.md`
- `backlog/epics.yaml`
- `backlog/traceability.csv`

## 完成定义

- [ ] 每个 Epic 至少关联一个用户角色、一个 API/界面和一个验收场景。
- [ ] P0 能独立形成从导入仓库到可证据化输出的闭环。
- [ ] 范围外清单明确，能防止在线 IDE 范围失控。
- [ ] 需求编号可在 backlog、测试和文档中追踪。

## 验证

1. 执行本模块单元、契约、集成、E2E、安全或性能测试。
2. 将需求、实现文件、测试和证据写入追踪矩阵。
3. 运行仓库级验证命令；本技能包自身使用：

```bash
python3 scripts/validate_skillpack.py
```

4. 输出 `system_wall_clock_eta_p50/p90` 与 `human_review_effort` 时必须分列。
5. 对未完成项、低置信度推断和外部依赖明确标注，禁止用“已完成”掩盖。
