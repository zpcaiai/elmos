# 增量分析、缓存与检查点 — Module Specification

## 1. Epic

- **Epic ID**：`EPIC-31`
- **Skill**：`elmos-incremental-analysis-cache`
- **批次**：`BATCH-08-cache-versioning-git`
- **目标**：让解析、图谱、解释、图表、文档和 PPT 能按最小影响范围重算，并在中断后继续。

## 2. 用户价值

实现内容寻址缓存、依赖失效、分阶段检查点和任务恢复。用于大型仓库、重复生成、转换中间状态和降低 Token/计算成本。

## 3. 功能需求

| ID | 需求 |
|---|---|
| `REQ-31-01` | 缓存键包含输入哈希、Schema、实现版本和租户隔离域。 |
| `REQ-31-02` | 失败结果仅短期负缓存并可手动清除。 |
| `REQ-31-03` | 检查点与幂等键配合避免重复提交 PR/通知。 |
| `REQ-31-04` | 支持本地、Redis、对象存储分层缓存。 |
| `REQ-31-05` | 人工锁定 artifact 不能被缓存结果覆盖。 |

## 4. API 触点

- `/api/v1/cache/stats`
- `/api/v1/checkpoints`
- `/api/v1/jobs/{id}/resume`

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

- `cache-key-spec.md`
- `checkpoint-schema.json`
- `cache-benchmark.md`

## 11. 任务清单

| Task | 标题 | 类型 | 优先级 |
|---|---|---|---|
| `ELMOS-PI-31-T01` | 为 ingest、parse、graph、flow、artifact、model call 定义确定性 cache key | implementation | P2 |
| `ELMOS-PI-31-T02` | 建立文件→symbol→graph view→claim→artifact block 的依赖索引 | implementation | P2 |
| `ELMOS-PI-31-T03` | 根据 Git diff、配置、规则、模型和模板变化计算失效范围 | implementation | P2 |
| `ELMOS-PI-31-T04` | 每个长阶段写原子检查点和已完成副作用 | implementation | P2 |
| `ELMOS-PI-31-T05` | 实现暂停、恢复、重试、取消和租约接管 | implementation | P2 |
| `ELMOS-PI-31-T06` | 记录命中率、节省 wall-clock、Token 和存储成本 | implementation | P2 |
| `ELMOS-PI-31-T07` | 实现权限、安全和不可信输入防护 | security | P2 |
| `ELMOS-PI-31-T08` | 接入日志、指标、Trace、错误分类和审计 | observability | P2 |
| `ELMOS-PI-31-T09` | 建立单元、契约、集成、E2E 与回归测试 | testing | P2 |
| `ELMOS-PI-31-T10` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P2 |

## 12. 验收标准

| ID | 验收标准 |
|---|---|
| `AC-31-01` | 相同输入重跑命中且输出哈希一致。 |
| `AC-31-02` | 修改单文件只失效预期下游。 |
| `AC-31-03` | worker 强制终止后可恢复。 |
| `AC-31-04` | 重复恢复不重复外部副作用。 |
| `AC-31-05` | 缓存指标可按项目/阶段查看。 |

## 13. 依赖

- `elmos-reference-architecture`
- `elmos-evidence-provenance`

## 14. 失败与恢复

- 将错误分类为 user-fixable、transient、capacity、permission、unsupported、internal。
- 可重试错误使用指数退避和最大次数；不可重试错误保留输入、日志和检查点。
- 恢复前验证 revision、配置、规则、模型、模板和权限是否仍兼容。
- 取消操作释放租约和临时资源，但保留审计与已确认 artifact。
