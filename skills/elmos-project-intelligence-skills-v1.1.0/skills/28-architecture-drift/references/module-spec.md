# 设计—代码—运行架构漂移检测 — Module Specification

## 1. Epic

- **Epic ID**：`EPIC-28`
- **Skill**：`elmos-architecture-drift`
- **批次**：`BATCH-07-search-impact-governance-analysis`
- **目标**：持续发现实际系统偏离架构意图的位置，并驱动评审、文档更新和改造任务。

## 2. 用户价值

比较设计架构、静态实现架构、运行时架构和目标架构，检测新增依赖、边界破坏、未声明服务和文档过期。

## 3. 功能需求

| ID | 需求 |
|---|---|
| `REQ-28-01` | 设计模型可来自 Structurizr/Diagram Spec/人工基线。 |
| `REQ-28-02` | 漂移检测绑定 base/head revision 与运行窗口。 |
| `REQ-28-03` | UI 需区分代码漂移和观测覆盖不足。 |
| `REQ-28-04` | 接受漂移需形成 ADR/审批。 |
| `REQ-28-05` | 结果可接入 PR 和周期扫描。 |

## 4. API 触点

- `/api/v1/drift`
- `/api/v1/architecture-baselines`
- `/api/v1/drift/{id}/decisions`

所有 API 必须：

- 使用 `/api/v1` 版本前缀或清晰的内部契约版本；
- 携带 `tenant_id`、`project_id`、`revision_id/analysis_run_id` 的服务端上下文；
- 支持幂等键、分页、错误码和权限校验；
- 不在错误消息中泄露代码、凭据或跨租户对象；
- 对长任务返回 `job_id`、状态、检查点和可恢复错误。

## 5. 主要领域实体

- `SearchIndex`
- `Question`
- `ImpactRun`
- `Rule`
- `Violation`
- `Risk`
- `SecurityFinding`

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

- 问答准确率
- 引用正确率
- 影响召回率
- 规则误报率
- 风险命中率

## 10. 交付物

- `drift-report.json`
- `architecture-diff.svg`

## 11. 任务清单

| Task | 标题 | 类型 | 优先级 |
|---|---|---|---|
| `ELMOS-PI-28-T01` | 规范化设计、静态和运行模型到统一语义 | implementation | P2 |
| `ELMOS-PI-28-T02` | 比较节点、关系、属性、所有权和安全边界 | implementation | P2 |
| `ELMOS-PI-28-T03` | 分类 expected change、undocumented change、violation、observation gap | implementation | P2 |
| `ELMOS-PI-28-T04` | 计算影响和严重度 | implementation | P2 |
| `ELMOS-PI-28-T05` | 生成图表 diff、证据和建议动作 | implementation | P2 |
| `ELMOS-PI-28-T06` | 支持确认、接受为新设计、拒绝或创建修复任务 | implementation | P2 |
| `ELMOS-PI-28-T07` | 实现权限、安全和不可信输入防护 | security | P2 |
| `ELMOS-PI-28-T08` | 接入日志、指标、Trace、错误分类和审计 | observability | P2 |
| `ELMOS-PI-28-T09` | 建立单元、契约、集成、E2E 与回归测试 | testing | P2 |
| `ELMOS-PI-28-T10` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P2 |

## 12. 验收标准

| ID | 验收标准 |
|---|---|
| `AC-28-01` | 基准漂移场景全部正确分类。 |
| `AC-28-02` | 误报可通过规则/override 解释性降低。 |
| `AC-28-03` | 接受变更生成可审计基线版本。 |
| `AC-28-04` | 文档和图表 stale 状态联动。 |
| `AC-28-05` | PR 中新增违规边能阻断。 |

## 13. 依赖

- `elmos-architecture-discovery`
- `elmos-runtime-trace-fusion`
- `elmos-architecture-rules`

## 14. 失败与恢复

- 将错误分类为 user-fixable、transient、capacity、permission、unsupported、internal。
- 可重试错误使用指数退避和最大次数；不可重试错误保留输入、日志和检查点。
- 恢复前验证 revision、配置、规则、模型、模板和权限是否仍兼容。
- 取消操作释放租约和临时资源，但保留审计与已确认 artifact。
