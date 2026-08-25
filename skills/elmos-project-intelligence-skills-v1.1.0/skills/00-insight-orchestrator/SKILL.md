---
name: elmos-insight-orchestrator
description: 规划、实施或验收 Elmos Project Intelligence Studio 全链路能力。用于跨多个子系统的复杂任务、批次推进、依赖协调和最终生产认证；不要用于只修改单个局部组件。
license: Proprietary-Elmos
compatibility: Agent Skills open format; compatible with OpenAI Codex/ChatGPT Skills
  and Claude Code. Requires repository read access; write or execution only when the
  task needs it.
metadata:
  version: 1.1.0
  category: orchestration
  title_zh: Project Intelligence Studio 总编排
  batch: BATCH-00-product-and-reference-architecture
  owner: elmos-project-intelligence
---

# Project Intelligence Studio 总编排

## 目标

把代码阅读、架构理解、流程发现、图表、文档、PPT、问答、影响分析和 Elmos 转换能力组织为可暂停、可恢复、可验证的统一工作流。

## 使用边界

- 当请求与本技能描述直接匹配时使用。
- 跨多个能力域、批次或需要长任务编排时，先调用 `elmos-insight-orchestrator`。
- 只实现本技能负责的完整垂直切片；不要把接口桩、TODO 或设计稿标记为完成。
- 读取 `references/module-spec.md` 后再修改代码。

## 输入

- Elmos 仓库路径或目标仓库
- 本次目标/批次
- 技术约束与部署模式
- 现有实现状态和测试结果

## 必须输出

- 执行计划与依赖图
- 按批次拆分的任务
- 实现变更
- 测试与证据
- 机器执行 ETA 与人工审核工作量分列

## 执行流程

1. 读取 AGENTS.md、CLAUDE.md、skillpack.yaml 和当前仓库状态。
2. 识别请求涉及的能力域，选择最少且足够的子技能。
3. 建立可执行计划、依赖、风险、回滚点和完成定义。
4. 按检查点实施；每个阶段产出代码、测试、文档和证据。
5. 运行包级验证与目标仓库测试，修复失败。
6. 生成完成报告，列出已完成、未完成、已知限制和下一批入口。

## 实施要求

- 长任务必须支持幂等、暂停、恢复、重试、取消与检查点。
- 所有生成结论必须可追踪到代码、配置、Schema、测试或运行证据。
- 不同 artifact 必须共享同一 Project Intelligence Graph 和 Evidence Graph。
- 系统运行时间使用机器 wall-clock P50/P90；人工审核时间单独列示。
- 不得用演示数据冒充真实项目分析结果。

## 安全与可信度约束

- 不静默覆盖用户代码、人工文档或已锁定图表节点。
- 没有证据时标记 Unknown 或 Inferred，不得补造架构。
- 不得扩大网络、密钥或仓库权限来绕过失败。
- 失败必须保留日志、检查点和可重放输入。

## 依赖技能

- 无；可作为起始技能。

## 预期交付物

- `IMPLEMENTATION_PLAN.md`
- `EXECUTION_REPORT.md`
- `evidence-bundle.json`

## 完成定义

- [ ] 子技能选择与依赖正确且可解释。
- [ ] 每个批次均有可运行测试和验收证据。
- [ ] 任务中断后可从最近检查点恢复且不重复副作用。
- [ ] 最终报告可追踪到 Commit、分析版本和 artifact 版本。
- [ ] 全包验证脚本返回成功。

## 验证

1. 执行本模块单元、契约、集成、E2E、安全或性能测试。
2. 将需求、实现文件、测试和证据写入追踪矩阵。
3. 运行仓库级验证命令；本技能包自身使用：

```bash
python3 scripts/validate_skillpack.py
```

4. 输出 `system_wall_clock_eta_p50/p90` 与 `human_review_effort` 时必须分列。
5. 对未完成项、低置信度推断和外部依赖明确标注，禁止用“已完成”掩盖。
