# 可观测性、SLO 与运营指标 — Module Specification

## 1. Epic

- **Epic ID**：`EPIC-37`
- **Skill**：`elmos-observability-slo`
- **批次**：`BATCH-10-scale-and-observability`
- **目标**：让质量、性能、成本、队列、失败、证据覆盖和用户体验可测量。

## 2. 用户价值

为接入、解析、图谱、问答、图表、文档、PPT、缓存和长任务建立指标、日志、Trace、SLO、告警和运营看板。

## 3. 功能需求

| ID | 需求 |
|---|---|
| `REQ-37-01` | 首要 SLO 覆盖代码打开、搜索问答、分析任务、artifact 生成和恢复。 |
| `REQ-37-02` | 机器 wall-clock ETA 的实际/预测均记录。 |
| `REQ-37-03` | 业务指标与技术指标分层。 |
| `REQ-37-04` | 日志使用结构化错误码。 |
| `REQ-37-05` | 审计日志与运营日志分离。 |

## 4. API 触点

- `/api/v1/operations/slos`
- `/api/v1/operations/metrics`
- `/api/v1/runbooks`

所有 API 必须：

- 使用 `/api/v1` 版本前缀或清晰的内部契约版本；
- 携带 `tenant_id`、`project_id`、`revision_id/analysis_run_id` 的服务端上下文；
- 支持幂等键、分页、错误码和权限校验；
- 不在错误消息中泄露代码、凭据或跨租户对象；
- 对长任务返回 `job_id`、状态、检查点和可恢复错误。

## 5. 主要领域实体

- `TelemetryEvent`
- `SLO`
- `Estimate`
- `Deployment`
- `Backup`
- `Certification`

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

- SLO 达成率
- ETA 校准误差
- RPO/RTO 达成率
- 告警噪声率

## 10. 交付物

- `observability-spec.md`
- `slo-catalog.yaml`
- `runbooks/`

## 11. 任务清单

| Task | 标题 | 类型 | 优先级 |
|---|---|---|---|
| `ELMOS-PI-37-T01` | 定义服务和用户旅程级 SLI | implementation | P2 |
| `ELMOS-PI-37-T02` | 统一 trace_id、job_id、project_id、analysis_run_id、artifact_id | implementation | P2 |
| `ELMOS-PI-37-T03` | 记录队列、阶段时长、重试、缓存、Token、模型、渲染和图查询指标 | implementation | P2 |
| `ELMOS-PI-37-T04` | 记录质量指标：解析率、图完整度、引用正确率、stale 率 | implementation | P2 |
| `ELMOS-PI-37-T05` | 建立 SLO、错误预算、告警和 Runbook | implementation | P2 |
| `ELMOS-PI-37-T06` | 实现敏感字段过滤与日志采样 | implementation | P2 |
| `ELMOS-PI-37-T07` | 实现权限、安全和不可信输入防护 | security | P2 |
| `ELMOS-PI-37-T08` | 接入日志、指标、Trace、错误分类和审计 | observability | P2 |
| `ELMOS-PI-37-T09` | 建立单元、契约、集成、E2E 与回归测试 | testing | P2 |
| `ELMOS-PI-37-T10` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P2 |

## 12. 验收标准

| ID | 验收标准 |
|---|---|
| `AC-37-01` | 关键请求可端到端 Trace。 |
| `AC-37-02` | 告警通过演练。 |
| `AC-37-03` | 仪表盘能定位慢阶段和成本来源。 |
| `AC-37-04` | 日志脱敏测试通过。 |
| `AC-37-05` | SLO 报告可按租户和版本比较。 |

## 13. 依赖

- `elmos-reference-architecture`

## 14. 失败与恢复

- 将错误分类为 user-fixable、transient、capacity、permission、unsupported、internal。
- 可重试错误使用指数退避和最大次数；不可重试错误保留输入、日志和检查点。
- 恢复前验证 revision、配置、规则、模型、模板和权限是否仍兼容。
- 取消操作释放租约和临时资源，但保留审计与已确认 artifact。
