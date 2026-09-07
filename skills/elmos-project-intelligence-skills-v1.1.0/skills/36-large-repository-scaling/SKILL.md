---
name: elmos-large-repository-scaling
description: 优化百万行、数万文件、Monorepo、多仓库系统的分片、调度、索引、图查询和用户体验。
license: Proprietary-Elmos
compatibility: Agent Skills open format; compatible with OpenAI Codex/ChatGPT Skills
  and Claude Code. Requires repository read access; write or execution only when the
  task needs it.
metadata:
  version: 1.1.0
  category: platform
  title_zh: 大型仓库与多仓库系统扩展
  batch: BATCH-10-scale-and-observability
  owner: elmos-project-intelligence
---

# 大型仓库与多仓库系统扩展

## 目标

在资源预算内处理大型项目，并提供渐进可用、可恢复和可预测的机器执行 ETA。

## 使用边界

- 当请求与本技能描述直接匹配时使用。
- 跨多个能力域、批次或需要长任务编排时，先调用 `elmos-insight-orchestrator`。
- 只实现本技能负责的完整垂直切片；不要把接口桩、TODO 或设计稿标记为完成。
- 读取 `references/module-spec.md` 后再修改代码。

## 输入

- repo metrics
- analysis DAG
- resource quotas
- SLOs

## 必须输出

- partition plan
- scheduler policy
- capacity model
- load-test report

## 执行流程

1. 按仓库、模块、语言、构建单元和内容哈希分片。
2. 定义优先索引：manifest→入口→高价值模块→全量。
3. 并行解析但串行提交一致图谱版本。
4. 对图查询实施分页、限制、近似和预计算。
5. 控制模型上下文、批处理、缓存和并发配额。
6. 执行 S/M/L/XL 仓库压测和故障注入。

## 实施要求

- UI 在部分分析完成时可用，并显示覆盖率。
- 任务调度支持公平性、租户配额和抢占。
- 对象/图/搜索索引有分区与生命周期。
- 机器 ETA 基于历史遥测校准 P50/P90。
- 超限时给出降级策略而非崩溃。

## 安全与可信度约束

- 不得为追求速度跳过证据和租户隔离。
- 不得无限展开调用图或把全仓库传给模型。
- 不得将预计耗时写成人工人日。

## 依赖技能

- `elmos-incremental-analysis-cache`
- `elmos-project-fingerprinting`

## 预期交付物

- `capacity-model.md`
- `load-test-scenarios.yaml`
- `scaling-report.md`

## 完成定义

- [ ] 目标规模压测达到吞吐和内存预算。
- [ ] 部分失败可重试单 shard。
- [ ] 增量 1% 变更成本显著低于全量。
- [ ] 公平调度避免大项目饿死小项目。
- [ ] ETA 校准误差有持续监控。

## 验证

1. 执行本模块单元、契约、集成、E2E、安全或性能测试。
2. 将需求、实现文件、测试和证据写入追踪矩阵。
3. 运行仓库级验证命令；本技能包自身使用：

```bash
python3 scripts/validate_skillpack.py
```

4. 输出 `system_wall_clock_eta_p50/p90` 与 `human_review_effort` 时必须分列。
5. 对未完成项、低置信度推断和外部依赖明确标注，禁止用“已完成”掩盖。
