# 产品范围与需求基线 — Module Specification

## 1. Epic

- **Epic ID**：`EPIC-01`
- **Skill**：`elmos-product-scope`
- **批次**：`BATCH-00-product-and-reference-architecture`
- **目标**：把模糊产品想法转化为有角色、有场景、有边界、有验收指标的生产级需求基线。

## 2. 用户价值

细化 Elmos 在线代码阅读、架构讲解、流程梳理、图表、文档和 PPT 等需求，并冻结可实施范围。用于 PRD、Epic、用户故事、优先级和范围控制。

## 3. 功能需求

| ID | 需求 |
|---|---|
| `REQ-01-01` | 覆盖个人、团队、企业私有化和 Elmos 转换场景。 |
| `REQ-01-02` | 明确静态分析与运行时分析的差异。 |
| `REQ-01-03` | 明确事实、推断、未知、建议四级可信度。 |
| `REQ-01-04` | 文档、图表与 PPT 必须支持增量更新和人工内容保护。 |
| `REQ-01-05` | 输出范围不得把完整通用 IDE 当作 P0。 |

## 4. API 触点

- `/api/v1/requirements`
- `/api/v1/traceability`

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

- `docs/01-product-requirements.md`
- `backlog/epics.yaml`
- `backlog/traceability.csv`

## 11. 任务清单

| Task | 标题 | 类型 | 优先级 |
|---|---|---|---|
| `ELMOS-PI-01-T01` | 识别用户角色、核心任务和痛点 | implementation | P0 |
| `ELMOS-PI-01-T02` | 将能力拆为 Read、Explain、Explore、Flow、Diagram、Document、Present、Impact、Debug、Learn | implementation | P0 |
| `ELMOS-PI-01-T03` | 定义每项能力的输入、输出、异常、权限和数据保留 | implementation | P0 |
| `ELMOS-PI-01-T04` | 按 P0-P3 排序并标注依赖 | implementation | P0 |
| `ELMOS-PI-01-T05` | 为每个 Story 编写可自动验证的完成条件 | implementation | P0 |
| `ELMOS-PI-01-T06` | 建立需求到技能、API、数据表和测试的追踪关系 | implementation | P0 |
| `ELMOS-PI-01-T07` | 实现权限、安全和不可信输入防护 | security | P0 |
| `ELMOS-PI-01-T08` | 接入日志、指标、Trace、错误分类和审计 | observability | P0 |
| `ELMOS-PI-01-T09` | 建立单元、契约、集成、E2E 与回归测试 | testing | P0 |
| `ELMOS-PI-01-T10` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P0 |

## 12. 验收标准

| ID | 验收标准 |
|---|---|
| `AC-01-01` | 每个 Epic 至少关联一个用户角色、一个 API/界面和一个验收场景。 |
| `AC-01-02` | P0 能独立形成从导入仓库到可证据化输出的闭环。 |
| `AC-01-03` | 范围外清单明确，能防止在线 IDE 范围失控。 |
| `AC-01-04` | 需求编号可在 backlog、测试和文档中追踪。 |

## 13. 依赖

- 无；可作为起始技能。

## 14. 失败与恢复

- 将错误分类为 user-fixable、transient、capacity、permission、unsupported、internal。
- 可重试错误使用指数退避和最大次数；不可重试错误保留输入、日志和检查点。
- 恢复前验证 revision、配置、规则、模型、模板和权限是否仍兼容。
- 取消操作释放租约和临时资源，但保留审计与已确认 artifact。
