# 参考架构与服务边界 — Module Specification

## 1. Epic

- **Epic ID**：`EPIC-02`
- **Skill**：`elmos-reference-architecture`
- **批次**：`BATCH-00-product-and-reference-architecture`
- **目标**：建立可扩展、可替换、可私有化部署的参考架构，避免 UI、分析引擎、模型和存储相互耦合。

## 2. 用户价值

设计或评审 Elmos Project Intelligence Studio 的生产级参考架构。用于服务拆分、数据存储、异步工作流、接口边界和技术选型。

## 3. 功能需求

| ID | 需求 |
|---|---|
| `REQ-02-01` | 默认 UI 为 Vue 3 + TypeScript + Monaco；解析核心优先 Rust/Tree-sitter；AI 编排可用 Python/LangGraph；企业接口可用 Java/Spring。 |
| `REQ-02-02` | 模型、图存储、搜索、渲染器必须通过 Adapter/Port 可替换。 |
| `REQ-02-03` | 长任务状态不能只保存在进程内。 |
| `REQ-02-04` | 所有 artifact 绑定 project revision、analysis run 和 generator version。 |
| `REQ-02-05` | 运行时 Trace 与静态图谱分开采集、统一关联。 |

## 4. API 触点

- `/api/v1/platform/capabilities`
- `/api/v1/service-catalog`

所有 API 必须：

- 使用 `/api/v1` 版本前缀或清晰的内部契约版本；
- 携带 `tenant_id`、`project_id`、`revision_id/analysis_run_id` 的服务端上下文；
- 支持幂等键、分页、错误码和权限校验；
- 不在错误消息中泄露代码、凭据或跨租户对象；
- 对长任务返回 `job_id`、状态、检查点和可恢复错误。

## 5. 主要领域实体

- `Requirement`
- `ArchitectureDecision`
- `ServiceCatalogEntry`

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

- 需求追踪覆盖率
- ADR 完整率
- 服务边界冲突数

## 10. 交付物

- `docs/02-reference-architecture.md`
- `docs/adr/`
- `diagrams/reference-architecture.yaml`

## 11. 任务清单

| Task | 标题 | 类型 | 优先级 |
|---|---|---|---|
| `ELMOS-PI-02-T01` | 定义 Browser、Control Plane、Analysis Plane、Artifact Plane 和 Storage Plane | implementation | P0 |
| `ELMOS-PI-02-T02` | 划分前端、项目 API、解析索引、图谱、AI 编排、渲染、导出和工作流服务 | implementation | P0 |
| `ELMOS-PI-02-T03` | 定义 PostgreSQL、图数据库、对象存储、搜索、缓存的职责和替换接口 | implementation | P0 |
| `ELMOS-PI-02-T04` | 定义 Temporal 工作流、事件总线和幂等键 | implementation | P0 |
| `ELMOS-PI-02-T05` | 定义多租户、网络边界、Secrets Broker 和审计 | implementation | P0 |
| `ELMOS-PI-02-T06` | 生成当前/目标架构图和 ADR | implementation | P0 |
| `ELMOS-PI-02-T07` | 实现权限、安全和不可信输入防护 | security | P0 |
| `ELMOS-PI-02-T08` | 接入日志、指标、Trace、错误分类和审计 | observability | P0 |
| `ELMOS-PI-02-T09` | 建立单元、契约、集成、E2E 与回归测试 | testing | P0 |
| `ELMOS-PI-02-T10` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P0 |

## 12. 验收标准

| ID | 验收标准 |
|---|---|
| `AC-02-01` | 服务边界无循环部署依赖。 |
| `AC-02-02` | 每个持久化数据类型有唯一主责存储。 |
| `AC-02-03` | 任何 worker 重启后工作流可恢复。 |
| `AC-02-04` | 架构支持 SaaS、单租户私有化和离线受限部署。 |
| `AC-02-05` | ADR 记录关键替代方案及弃用原因。 |

## 13. 依赖

- `elmos-product-scope`

## 14. 失败与恢复

- 将错误分类为 user-fixable、transient、capacity、permission、unsupported、internal。
- 可重试错误使用指数退避和最大次数；不可重试错误保留输入、日志和检查点。
- 恢复前验证 revision、配置、规则、模型、模板和权限是否仍兼容。
- 取消操作释放租约和临时资源，但保留审计与已确认 artifact。
