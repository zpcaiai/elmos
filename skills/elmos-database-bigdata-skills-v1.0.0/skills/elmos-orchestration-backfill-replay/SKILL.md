---
name: elmos-orchestration-backfill-replay
description: 生成 Airflow/Dagster/Temporal 等编排 DAG，覆盖依赖、调度、事件触发、回填、重试和恢复。
version: 1.0.0
group: bigdata-core
dependencies: ["elmos-ingestion-connector-planner", "elmos-batch-processing-generator", "elmos-stream-processing-generator", "elmos-data-quality-observability"]
triggers: ["调度数据管道", "历史回填或事件重放", "任务暂停恢复"]
outputs: ["orchestration/", "backfill-plan.json", "replay-runbook.md", "idempotency-policy.json"]
---

# 数据编排、回填、重放与幂等恢复

## 目标

生成 Airflow/Dagster/Temporal 等编排 DAG，覆盖依赖、调度、事件触发、回填、重试和恢复。

## 适用触发条件

- 调度数据管道
- 历史回填或事件重放
- 任务暂停恢复

## 输入

- pipeline DAG
- 依赖与 SLO
- 历史分区/offset
- 平台约束

## 执行流程

1. **ORCH-001** — 区分数据作业编排与 Elmos 长任务控制：数据 DAG 可用 Airflow/Dagster，Elmos 控制面可用 Temporal。
2. **ORCH-002** — 按资产依赖、时间、事件和审批设计 DAG，不用 sleep/polling 占 worker。
3. **ORCH-003** — 为节点定义幂等键、输入快照、输出提交、重试分类、超时和补偿。
4. **ORCH-004** — 设计分区 backfill、事件 replay、范围锁、并发限制和下游影响预览。
5. **ORCH-005** — 隔离历史回填与实时结果，使用版本/命名空间/原子切换。
6. **ORCH-006** — 持久化进度、offset、成本、日志、lineage 和证据；验证重复触发与故障恢复。

## 强制决策规则

- 先执行硬约束过滤，再做软评分；安全、合规、数据完整性和明确 SLO 不可被总分覆盖。
- 所有外部能力、版本、兼容性与性能声明必须绑定注册表或运行证据；模型记忆不能作为生产证据。
- 默认优先最简单、可运维、可恢复的方案；新增数据库或引擎必须证明其量化必要性。
- 多租户数据、缓存、日志、指标、密钥和证据必须按 tenant_id 隔离。
- 所有副作用任务必须有 idempotency_key、恢复点、重试分类和回滚/补偿语义。
- 输出必须区分 implemented、configured、tested、verified、certified。

## 必需产物

- `orchestration/`
- `backfill-plan.json`
- `replay-runbook.md`
- `idempotency-policy.json`

## 验收标准

- DAG 可暂停恢复重试取消且幂等。
- 回填范围/资源/影响可预览。
- 历史与实时不互相污染。
- 节点进度可持久化。

## 失败、降级与恢复

副作用不可幂等时引入事务、staging 或人工门禁，不允许无限自动重试。

失败时必须保存已完成节点、输入快照、输出校验和、日志、成本、模型调用、缺陷和剩余 DAG；恢复从最近幂等节点继续。

## 完成检查表

- [ ] **ORCH-007** — 输入和授权范围已固化为不可变快照。
- [ ] **ORCH-008** — 需求、假设、SLO、租户和安全边界已显式记录。
- [ ] **ORCH-009** — 选择或生成结果可由机器读取并通过 Schema 校验。
- [ ] **ORCH-010** — 关键决策有证据、备选方案、风险和回退条件。
- [ ] **ORCH-011** — 测试、监控、成本与运行手册已随代码生成。
- [ ] **ORCH-012** — 未验证能力未被标记为生产完成。
