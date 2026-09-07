# 功能思维导图与业务能力地图 — Module Specification

## 1. Epic

- **Epic ID**：`EPIC-14`
- **Skill**：`elmos-business-capability-map`
- **批次**：`BATCH-04-architecture-flow-data`
- **目标**：建立需求—功能—页面—API—代码—数据—测试的端到端追踪。

## 2. 用户价值

从页面、API、服务、数据和已有需求发现业务域、能力、功能模块和子功能，并生成双向可追踪思维导图。

## 3. 功能需求

| ID | 需求 |
|---|---|
| `REQ-14-01` | 功能节点必须有稳定 ID 与版本。 |
| `REQ-14-02` | 业务能力与技术模块不能混为同一层。 |
| `REQ-14-03` | 支持多产品、多租户和 Feature Flag。 |
| `REQ-14-04` | 支持从代码反查功能、从功能跳代码。 |
| `REQ-14-05` | 未映射代码和未实现需求需单独列出。 |

## 4. API 触点

- `/api/v1/capabilities`
- `/api/v1/features`
- `/api/v1/feature-traceability`

所有 API 必须：

- 使用 `/api/v1` 版本前缀或清晰的内部契约版本；
- 携带 `tenant_id`、`project_id`、`revision_id/analysis_run_id` 的服务端上下文；
- 支持幂等键、分页、错误码和权限校验；
- 不在错误消息中泄露代码、凭据或跨租户对象；
- 对长任务返回 `job_id`、状态、检查点和可恢复错误。

## 5. 主要领域实体

- `ArchitectureModel`
- `Capability`
- `Flow`
- `DataAsset`
- `Integration`
- `RuntimeObservation`

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

- 入口覆盖率
- 流程步骤召回率
- 血缘准确率
- 架构节点置信度

## 10. 交付物

- `capability-map.json`
- `functional-mindmap.mm.json`
- `feature-traceability.csv`

## 11. 任务清单

| Task | 标题 | 类型 | 优先级 |
|---|---|---|---|
| `ELMOS-PI-14-T01` | 识别 Actor、业务域、业务能力、功能模块和子功能 | implementation | P1 |
| `ELMOS-PI-14-T02` | 将页面、API、事件、代码、数据表、权限和测试挂接到功能节点 | implementation | P1 |
| `ELMOS-PI-14-T03` | 使用命名、调用链和文档证据生成候选功能 | implementation | P1 |
| `ELMOS-PI-14-T04` | 让用户确认、合并、拆分、重命名和排序 | implementation | P1 |
| `ELMOS-PI-14-T05` | 计算实现覆盖、测试覆盖、风险和转换状态 | implementation | P1 |
| `ELMOS-PI-14-T06` | 生成 Markmap、树形图、矩阵和可编辑 JSON | implementation | P1 |
| `ELMOS-PI-14-T07` | 实现权限、安全和不可信输入防护 | security | P1 |
| `ELMOS-PI-14-T08` | 接入日志、指标、Trace、错误分类和审计 | observability | P1 |
| `ELMOS-PI-14-T09` | 建立单元、契约、集成、E2E 与回归测试 | testing | P1 |
| `ELMOS-PI-14-T10` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P1 |

## 12. 验收标准

| ID | 验收标准 |
|---|---|
| `AC-14-01` | 主要用户流程功能均可映射到 API/代码/数据。 |
| `AC-14-02` | 功能图节点可双向导航。 |
| `AC-14-03` | 重复功能候选可识别。 |
| `AC-14-04` | 未映射比例可量化。 |
| `AC-14-05` | 导出后可重新导入且不丢稳定 ID。 |

## 13. 依赖

- `elmos-architecture-discovery`
- `elmos-evidence-provenance`

## 14. 失败与恢复

- 将错误分类为 user-fixable、transient、capacity、permission、unsupported、internal。
- 可重试错误使用指数退避和最大次数；不可重试错误保留输入、日志和检查点。
- 恢复前验证 revision、配置、规则、模型、模板和权限是否仍兼容。
- 取消操作释放租约和临时资源，但保留审计与已确认 artifact。
