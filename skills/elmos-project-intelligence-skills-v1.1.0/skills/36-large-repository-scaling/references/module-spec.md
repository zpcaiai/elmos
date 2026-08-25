# 大型仓库与多仓库系统扩展 — Module Specification

## 1. Epic

- **Epic ID**：`EPIC-36`
- **Skill**：`elmos-large-repository-scaling`
- **批次**：`BATCH-10-scale-and-observability`
- **目标**：在资源预算内处理大型项目，并提供渐进可用、可恢复和可预测的机器执行 ETA。

## 2. 用户价值

优化百万行、数万文件、Monorepo、多仓库系统的分片、调度、索引、图查询和用户体验。

## 3. 功能需求

| ID | 需求 |
|---|---|
| `REQ-36-01` | UI 在部分分析完成时可用，并显示覆盖率。 |
| `REQ-36-02` | 任务调度支持公平性、租户配额和抢占。 |
| `REQ-36-03` | 对象/图/搜索索引有分区与生命周期。 |
| `REQ-36-04` | 机器 ETA 基于历史遥测校准 P50/P90。 |
| `REQ-36-05` | 超限时给出降级策略而非崩溃。 |

## 4. API 触点

- `/api/v1/capacity/plans`
- `/api/v1/scheduler/queues`

所有 API 必须：

- 使用 `/api/v1` 版本前缀或清晰的内部契约版本；
- 携带 `tenant_id`、`project_id`、`revision_id/analysis_run_id` 的服务端上下文；
- 支持幂等键、分页、错误码和权限校验；
- 不在错误消息中泄露代码、凭据或跨租户对象；
- 对长任务返回 `job_id`、状态、检查点和可恢复错误。

## 5. 主要领域实体

- `CacheEntry`
- `Checkpoint`
- `ArtifactLock`
- `GitDelivery`
- `SchedulerLease`

实体必须包含必要的：

- stable ID；
- tenant/project scope；
- revision 或 version；
- created/updated/actor；
- provenance/evidence；
- optimistic lock 或 immutable version。

## 6. 事件与异步工作

建议事件命名：`elmos.project-intelligence.<domain>.<event>.v1`。

- 开始、完成、失败、取消和检查点事件必须可区分；
- 事件携带引用 ID，不携带大段源代码；
- 消费者必须幂等；
- 外部副作用保存 idempotency key；
- poison message 进入隔离队列并生成可操作诊断。

## 7. UI/交互要求

- 页面必须显示 revision、分析覆盖、可信度和数据新鲜度。
- 长任务显示阶段、已完成单位、P50/P90 机器 ETA、重试和恢复入口。
- 用户可从结论跳转证据；无证据时显示 Unknown/Inferred。
- 人工编辑、锁定、审批和自动生成状态视觉区分。
- 权限不足不得通过搜索、缩略图、缓存或深链泄漏信息。

## 8. 非功能要求

- API、图查询、渲染和长任务分别定义 p50/p95/p99。
- 支持水平扩展、背压、配额和 graceful degradation。
- 所有持久化 Schema 与事件有版本和迁移路径。
- 安全默认拒绝、Secrets Broker、审计、传输/静态加密。
- 可通过内容哈希、版本和输入 manifest 重现。

## 9. 关键指标

- 缓存命中率
- 恢复成功率
- 重复副作用数
- 队列等待 p95

## 10. 交付物

- `capacity-model.md`
- `load-test-scenarios.yaml`
- `scaling-report.md`

## 11. 任务清单

| Task | 标题 | 类型 | 优先级 |
|---|---|---|---|
| `ELMOS-PI-36-T01` | 按仓库、模块、语言、构建单元和内容哈希分片 | implementation | P2 |
| `ELMOS-PI-36-T02` | 定义优先索引：manifest→入口→高价值模块→全量 | implementation | P2 |
| `ELMOS-PI-36-T03` | 并行解析但串行提交一致图谱版本 | implementation | P2 |
| `ELMOS-PI-36-T04` | 对图查询实施分页、限制、近似和预计算 | implementation | P2 |
| `ELMOS-PI-36-T05` | 控制模型上下文、批处理、缓存和并发配额 | implementation | P2 |
| `ELMOS-PI-36-T06` | 执行 S/M/L/XL 仓库压测和故障注入 | implementation | P2 |
| `ELMOS-PI-36-T07` | 实现权限、安全和不可信输入防护 | security | P2 |
| `ELMOS-PI-36-T08` | 接入日志、指标、Trace、错误分类和审计 | observability | P2 |
| `ELMOS-PI-36-T09` | 建立单元、契约、集成、E2E 与回归测试 | testing | P2 |
| `ELMOS-PI-36-T10` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P2 |

## 12. 验收标准

| ID | 验收标准 |
|---|---|
| `AC-36-01` | 目标规模压测达到吞吐和内存预算。 |
| `AC-36-02` | 部分失败可重试单 shard。 |
| `AC-36-03` | 增量 1% 变更成本显著低于全量。 |
| `AC-36-04` | 公平调度避免大项目饿死小项目。 |
| `AC-36-05` | ETA 校准误差有持续监控。 |

## 13. 依赖

- `elmos-incremental-analysis-cache`
- `elmos-project-fingerprinting`

## 14. 失败与恢复

- 将错误分类为 user-fixable、transient、capacity、permission、unsupported、internal。
- 可重试错误使用指数退避和最大次数；不可重试错误保留输入、日志和检查点。
- 恢复前验证 revision、配置、规则、模型、模板和权限是否仍兼容。
- 取消操作释放租约和临时资源，但保留审计与已确认 artifact。
