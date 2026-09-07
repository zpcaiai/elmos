# ELMOS 构建缓存、文件暂存与 SOTA 自适应缓存 Skills 包

版本：**1.1.0**（2026-08-19）

本包在 v1.0.0 的构建缓存、项目生成文件暂存、中间状态、断点恢复和原子发布基础上，新增 **7 个 SOTA 缓存优化 Skills**。系统不再把 LRU 或任何单一算法当成万能默认，而是按缓存层级、对象大小、复用距离、重算成本、模型 Token 成本、网络代价和转换 DAG 的未来访问计划进行自适应选择。

## 默认算法组合

| 缓存层 | 默认强基线 | 自适应候选 | 主要目标 |
|---|---|---|---|
| L0 进程内元数据 | W-TinyLFU | SIEVE | 高频小对象与低延迟 |
| L1 本地 CAS / Action Cache | S3-FIFO 或 SIEVE | Merlin / S4-FIFO 风格参数调节 | 扫描抗性、并发吞吐、对象命中 |
| L2 远程共享 CAS | 大小感知 TinyLFU / GDSF | 自适应策略编排 | 字节命中、重算成本、网络成本 |
| 活跃任务与检查点 | DAG 未来复用保护 | Next-use 预取与本地性调度 | 关键路径和恢复速度 |
| 语义相似复用 | 仅候选缓存 | 成本感知语义检索 | 提供候选；必须重新验证 |

## 核心原则

- **没有“全场景唯一 SOTA”**：所有策略必须在真实 ELMOS Trace 上等容量回放。
- **优化避免的工作，而非只优化命中次数**：同时看 Object Hit、Byte Hit、避免计算、Token 节省、关键路径节省和恢复成本。
- **已知 DAG 优先于盲目预测**：转换计划已经知道未来节点需要哪些 AST、IR、代码、编译产物和测试证据，可做 Next-use 保护和预取。
- **学习只在控制面**：S4-FIFO 风格模型只调有限参数或选择策略 epoch，不参与 ActionKey 正确性判断。
- **任何模型可立即回退**：低置信、漂移、遥测缺失、OOD 或性能回退时，自动切回 S3-FIFO/SIEVE/W-TinyLFU 固定策略。
- **项目生成文件暂存仍是强约束**：生成文件必须经历 `RESERVED → WRITING → SEALED → CAS_PROMOTED → TREE_INCLUDED → PUBLISHED`，不能因追求命中率绕过校验和原子发布。

## 新增 7 个 Skills

1. `elmos-cache-trace-replay-simulator`
2. `elmos-sota-cache-policy-portfolio`
3. `elmos-dag-aware-cache-prefetch`
4. `elmos-cost-aware-cache-admission`
5. `elmos-adaptive-cache-policy-orchestrator`
6. `elmos-learning-augmented-cache-control`
7. `elmos-cache-autotuning-certification`

总计 **31 个可执行 Skills**。

## 包内新增工程资产

- SOTA 算法选型矩阵和研究来源；
- Trace、Policy、Benchmark Report JSON Schema；
- SOTA 生产配置模板；
- SIEVE、S3-FIFO、W-TinyLFU、GDSF 教学型参考实现；
- 多策略回放 Simulator；
- DAG next-use 预取与保护参考实现；
- 真实/合成 Trace 验收矩阵；
- Shadow、Canary、回退和生产认证流程。

## 安装与校验

```bash
./validate.sh
./install.sh --all
```

默认不会覆盖现有同名 Skill；需要覆盖时显式使用：

```bash
./install.sh --all --overwrite
```

执行实现前，应先读取 `AGENTS.md`、`manifest.json`、两份主规范、研究矩阵和所选 Skill 的依赖项。论文结果不能替代 ELMOS 自己的 Trace 回放与生产证据。
