# 符号、引用与调用图 — Module Specification

## 1. Epic

- **Epic ID**：`EPIC-06`
- **Skill**：`elmos-symbol-code-graph`
- **批次**：`BATCH-02-graphs-and-evidence`
- **目标**：把离散 Code IR 连接为可查询、可增量更新的 Code Graph。

## 2. 用户价值

构建定义、引用、继承、实现、调用、读写和跨语言边。用于语义导航、调用链、影响分析和架构抽取。

## 3. 功能需求

| ID | 需求 |
|---|---|
| `REQ-06-01` | 支持静态精确边、静态候选边和运行时确认边并存。 |
| `REQ-06-02` | Graph ID 稳定，跨增量 run 可复用。 |
| `REQ-06-03` | 查询必须支持 revision 和 branch 隔离。 |
| `REQ-06-04` | 边删除必须基于新 revision 正确回收。 |
| `REQ-06-05` | 高基数关系支持分页和采样。 |

## 4. API 触点

- `/api/v1/symbols`
- `/api/v1/references`
- `/api/v1/call-hierarchy`
- `/api/v1/type-hierarchy`

所有 API 必须：

- 使用 `/api/v1` 版本前缀或清晰的内部契约版本；
- 携带 `tenant_id`、`project_id`、`revision_id/analysis_run_id` 的服务端上下文；
- 支持幂等键、分页、错误码和权限校验；
- 不在错误消息中泄露代码、凭据或跨租户对象；
- 对长任务返回 `job_id`、状态、检查点和可恢复错误。

## 5. 主要领域实体

- `AnalysisRun`
- `Symbol`
- `GraphNode`
- `GraphEdge`
- `Claim`
- `Evidence`

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

- 解析成功率
- 未解析边比例
- 图谱完整度
- 证据覆盖率
- 增量一致性

## 10. 交付物

- `code-graph-snapshot.json`
- `unresolved-edges.json`

## 11. 任务清单

| Task | 标题 | 类型 | 优先级 |
|---|---|---|---|
| `ELMOS-PI-06-T01` | 创建文件、模块、包、类型、函数和字段节点 | implementation | P0 |
| `ELMOS-PI-06-T02` | 解析定义/引用、继承/实现、调用者/被调用者 | implementation | P0 |
| `ELMOS-PI-06-T03` | 识别依赖注入、反射注册、路由绑定和 ORM 映射 | implementation | P0 |
| `ELMOS-PI-06-T04` | 构建前端页面到 API、API 到服务、服务到数据库的跨层边 | implementation | P0 |
| `ELMOS-PI-06-T05` | 为边保存解析策略、证据和置信度 | implementation | P0 |
| `ELMOS-PI-06-T06` | 计算 SCC、中心性、扇入扇出和循环依赖 | implementation | P0 |
| `ELMOS-PI-06-T07` | 实现权限、安全和不可信输入防护 | security | P0 |
| `ELMOS-PI-06-T08` | 接入日志、指标、Trace、错误分类和审计 | observability | P0 |
| `ELMOS-PI-06-T09` | 建立单元、契约、集成、E2E 与回归测试 | testing | P0 |
| `ELMOS-PI-06-T10` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P0 |

## 12. 验收标准

| ID | 验收标准 |
|---|---|
| `AC-06-01` | Go to definition、find references 和 call hierarchy 在基准项目通过。 |
| `AC-06-02` | 循环依赖检测与人工基线一致。 |
| `AC-06-03` | 每条边可返回 evidence 与解析方法。 |
| `AC-06-04` | 增量更新后无幽灵边。 |
| `AC-06-05` | 图查询 p95 达到 SLO。 |

## 13. 依赖

- `elmos-multilanguage-parsing`

## 14. 失败与恢复

- 将错误分类为 user-fixable、transient、capacity、permission、unsupported、internal。
- 可重试错误使用指数退避和最大次数；不可重试错误保留输入、日志和检查点。
- 恢复前验证 revision、配置、规则、模型、模板和权限是否仍兼容。
- 取消操作释放租约和临时资源，但保留审计与已确认 artifact。
