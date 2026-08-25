# 统一图表语义规范 — Module Specification

## 1. Epic

- **Epic ID**：`EPIC-19`
- **Skill**：`elmos-diagram-spec-engine`
- **批次**：`BATCH-05-diagram-platform`
- **目标**：以可版本化的中立 DSL 表达节点、边、分组、证据、布局约束和交互，避免图表只剩不可维护图片。

## 2. 用户价值

定义架构图、流程图、思维导图、数据图、API 图、部署图和安全图的统一 Diagram Spec。用于不同渲染器、编辑器和导出格式共享语义。

## 3. 功能需求

| ID | 需求 |
|---|---|
| `REQ-19-01` | Diagram Spec 是权威可编辑源，SVG/PNG 只是派生物。 |
| `REQ-19-02` | 节点/边 ID 跨再生成稳定。 |
| `REQ-19-03` | 显示属性与语义属性分离。 |
| `REQ-19-04` | 每个 profile 定义必需字段和允许关系。 |
| `REQ-19-05` | Schema 版本有迁移工具。 |

## 4. API 触点

- `/api/v1/diagram-specs`
- `/api/v1/diagram-profiles`
- `/api/v1/diagram-specs/validate`

所有 API 必须：

- 使用 `/api/v1` 版本前缀或清晰的内部契约版本；
- 携带 `tenant_id`、`project_id`、`revision_id/analysis_run_id` 的服务端上下文；
- 支持幂等键、分页、错误码和权限校验；
- 不在错误消息中泄露代码、凭据或跨租户对象；
- 对长任务返回 `job_id`、状态、检查点和可恢复错误。

## 5. 主要领域实体

- `Artifact`
- `ArtifactVersion`
- `DiagramSpec`
- `DocumentBlock`
- `SlideElement`
- `EvidenceBinding`

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

- 生成成功率
- 引用有效率
- 人工锁定保留率
- 渲染 p95
- stale 率

## 10. 交付物

- `schemas/diagram-spec.schema.json`
- `diagram-profiles/`

## 11. 任务清单

| Task | 标题 | 类型 | 优先级 |
|---|---|---|---|
| `ELMOS-PI-19-T01` | 定义 diagram metadata、nodes、edges、groups、ports、views 和 evidence refs | implementation | P1 |
| `ELMOS-PI-19-T02` | 为 C4、BPMN、Sequence、State、ER、DFD、Mindmap、Deployment 等定义 profile | implementation | P1 |
| `ELMOS-PI-19-T03` | 定义折叠、聚合、分页、布局 hint 和视觉语义 | implementation | P1 |
| `ELMOS-PI-19-T04` | 定义人工锁定、注释和版本 diff | implementation | P1 |
| `ELMOS-PI-19-T05` | 实现 JSON Schema 和语义校验器 | implementation | P1 |
| `ELMOS-PI-19-T06` | 提供从 Intelligence Graph 到 Diagram Spec 的投影器 | implementation | P1 |
| `ELMOS-PI-19-T07` | 实现权限、安全和不可信输入防护 | security | P1 |
| `ELMOS-PI-19-T08` | 接入日志、指标、Trace、错误分类和审计 | observability | P1 |
| `ELMOS-PI-19-T09` | 建立单元、契约、集成、E2E 与回归测试 | testing | P1 |
| `ELMOS-PI-19-T10` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P1 |

## 12. 验收标准

| ID | 验收标准 |
|---|---|
| `AC-19-01` | 所有目录中的核心图表类型通过 Schema。 |
| `AC-19-02` | 相同图谱与参数生成稳定 element ID。 |
| `AC-19-03` | 无效边和孤立证据引用被拒绝。 |
| `AC-19-04` | Spec 可由至少两个渲染器消费。 |
| `AC-19-05` | 版本迁移保持语义等价。 |

## 13. 依赖

- `elmos-project-intelligence-graph`

## 14. 失败与恢复

- 将错误分类为 user-fixable、transient、capacity、permission、unsupported、internal。
- 可重试错误使用指数退避和最大次数；不可重试错误保留输入、日志和检查点。
- 恢复前验证 revision、配置、规则、模型、模板和权限是否仍兼容。
- 取消操作释放租约和临时资源，但保留审计与已确认 artifact。
