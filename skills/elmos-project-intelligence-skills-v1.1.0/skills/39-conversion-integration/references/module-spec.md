# 与 Elmos 生成、转换、翻新引擎集成 — Module Specification

## 1. Epic

- **Epic ID**：`EPIC-39`
- **Skill**：`elmos-conversion-integration`
- **批次**：`BATCH-11-testing-conversion-estimation`
- **目标**：形成导入—理解—转换—审阅—验证—文档/PPT—交付的统一闭环。

## 2. 用户价值

把 Project Intelligence Studio 与整项目生成、多语言转换、Spring 翻新、Semantic IR、规则、自动修复、双运行和认证流程连接。

## 3. 功能需求

| ID | 需求 |
|---|---|
| `REQ-39-01` | 支持 Java、Kotlin、Python、C#、Go、Rust、C++、PHP、TypeScript/React、Objective-C、Swift、Flutter、JavaScript 目标矩阵。 |
| `REQ-39-02` | Source/Target/IR/Evidence 三至四栏可联动。 |
| `REQ-39-03` | 转换任务共享缓存、检查点、成本与 ETA。 |
| `REQ-39-04` | 功能保持、行为等价、性能等价分别建证据。 |
| `REQ-39-05` | Strangler、双运行和回滚状态可视化。 |

## 4. API 触点

- `/api/v1/conversions/{id}/mapping`
- `/api/v1/conversions/{id}/comparison`
- `/api/v1/certification`

所有 API 必须：

- 使用 `/api/v1` 版本前缀或清晰的内部契约版本；
- 携带 `tenant_id`、`project_id`、`revision_id/analysis_run_id` 的服务端上下文；
- 支持幂等键、分页、错误码和权限校验；
- 不在错误消息中泄露代码、凭据或跨租户对象；
- 对长任务返回 `job_id`、状态、检查点和可恢复错误。

## 5. 主要领域实体

- `ConversionTask`
- `SourceTargetMapping`
- `RuleHit`
- `RepairAttempt`

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

- 映射覆盖率
- 行为等价通过率
- 修复成功率
- 中断恢复率

## 10. 交付物

- `conversion-mapping.json`
- `modernization-report.md`
- `migration-presentation.pptx`

## 11. 任务清单

| Task | 标题 | 类型 | 优先级 |
|---|---|---|---|
| `ELMOS-PI-39-T01` | 让 Elmos 生成/转换中的中间 revision 直接进入阅读器 | implementation | P3 |
| `ELMOS-PI-39-T02` | 连接 Source Symbol、Semantic IR、Target Symbol 和 Rule 命中 | implementation | P3 |
| `ELMOS-PI-39-T03` | 生成模块、API、数据、流程和架构前后映射 | implementation | P3 |
| `ELMOS-PI-39-T04` | 显示未支持、低置信度、编译/测试失败和自动修复历史 | implementation | P3 |
| `ELMOS-PI-39-T05` | 将人工修改提炼为候选规则但不自动发布 | implementation | P3 |
| `ELMOS-PI-39-T06` | 完成后生成迁移文档、图表、PPT 和证据包 | implementation | P3 |
| `ELMOS-PI-39-T07` | 实现权限、安全和不可信输入防护 | security | P3 |
| `ELMOS-PI-39-T08` | 接入日志、指标、Trace、错误分类和审计 | observability | P3 |
| `ELMOS-PI-39-T09` | 建立单元、契约、集成、E2E 与回归测试 | testing | P3 |
| `ELMOS-PI-39-T10` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P3 |

## 12. 验收标准

| ID | 验收标准 |
|---|---|
| `AC-39-01` | 源目标主要 symbol 映射可导航。 |
| `AC-39-02` | 转换前后图表与文档一致。 |
| `AC-39-03` | 失败定位能跳到规则、代码和测试。 |
| `AC-39-04` | 中断恢复不丢中间状态。 |
| `AC-39-05` | E1-E5 认证状态由证据驱动。 |

## 13. 依赖

- `elmos-project-intelligence-graph`
- `elmos-impact-analysis`
- `elmos-incremental-analysis-cache`

## 14. 失败与恢复

- 将错误分类为 user-fixable、transient、capacity、permission、unsupported、internal。
- 可重试错误使用指数退避和最大次数；不可重试错误保留输入、日志和检查点。
- 恢复前验证 revision、配置、规则、模型、模板和权限是否仍兼容。
- 取消操作释放租约和临时资源，但保留审计与已确认 artifact。
