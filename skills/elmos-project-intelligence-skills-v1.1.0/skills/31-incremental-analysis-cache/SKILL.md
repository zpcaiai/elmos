---
name: elmos-incremental-analysis-cache
description: 实现内容寻址缓存、依赖失效、分阶段检查点和任务恢复。用于大型仓库、重复生成、转换中间状态和降低 Token/计算成本。
license: Proprietary-Elmos
compatibility: Agent Skills open format; compatible with OpenAI Codex/ChatGPT Skills
  and Claude Code. Requires repository read access; write or execution only when the
  task needs it.
metadata:
  version: 1.1.0
  category: platform
  title_zh: 增量分析、缓存与检查点
  batch: BATCH-08-cache-versioning-git
  owner: elmos-project-intelligence
---

# 增量分析、缓存与检查点

## 目标

让解析、图谱、解释、图表、文档和 PPT 能按最小影响范围重算，并在中断后继续。

## 使用边界

- 当请求与本技能描述直接匹配时使用。
- 跨多个能力域、批次或需要长任务编排时，先调用 `elmos-insight-orchestrator`。
- 只实现本技能负责的完整垂直切片；不要把接口桩、TODO 或设计稿标记为完成。
- 读取 `references/module-spec.md` 后再修改代码。

## 输入

- revision diff
- task DAG
- artifact dependencies
- cache policy

## 必须输出

- cache keys
- invalidation plan
- checkpoints
- resume tokens
- cache metrics

## 执行流程

1. 为 ingest、parse、graph、flow、artifact、model call 定义确定性 cache key。
2. 建立文件→symbol→graph view→claim→artifact block 的依赖索引。
3. 根据 Git diff、配置、规则、模型和模板变化计算失效范围。
4. 每个长阶段写原子检查点和已完成副作用。
5. 实现暂停、恢复、重试、取消和租约接管。
6. 记录命中率、节省 wall-clock、Token 和存储成本。

## 实施要求

- 缓存键包含输入哈希、Schema、实现版本和租户隔离域。
- 失败结果仅短期负缓存并可手动清除。
- 检查点与幂等键配合避免重复提交 PR/通知。
- 支持本地、Redis、对象存储分层缓存。
- 人工锁定 artifact 不能被缓存结果覆盖。

## 安全与可信度约束

- 不得跨租户共享含代码或解释内容的缓存。
- 不得以时间戳作为唯一失效机制。
- 恢复前必须验证输入 revision 未变化。

## 依赖技能

- `elmos-reference-architecture`
- `elmos-evidence-provenance`

## 预期交付物

- `cache-key-spec.md`
- `checkpoint-schema.json`
- `cache-benchmark.md`

## 完成定义

- [ ] 相同输入重跑命中且输出哈希一致。
- [ ] 修改单文件只失效预期下游。
- [ ] worker 强制终止后可恢复。
- [ ] 重复恢复不重复外部副作用。
- [ ] 缓存指标可按项目/阶段查看。

## 验证

1. 执行本模块单元、契约、集成、E2E、安全或性能测试。
2. 将需求、实现文件、测试和证据写入追踪矩阵。
3. 运行仓库级验证命令；本技能包自身使用：

```bash
python3 scripts/validate_skillpack.py
```

4. 输出 `system_wall_clock_eta_p50/p90` 与 `human_review_effort` 时必须分列。
5. 对未完成项、低置信度推断和外部依赖明确标注，禁止用“已完成”掩盖。
