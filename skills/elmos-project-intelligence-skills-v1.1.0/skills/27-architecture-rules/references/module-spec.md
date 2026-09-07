# 架构规则与策略引擎 — Module Specification

## 1. Epic

- **Epic ID**：`EPIC-27`
- **Skill**：`elmos-architecture-rules`
- **批次**：`BATCH-07-search-impact-governance-analysis`
- **目标**：将架构原则转为可版本化、可测试、可豁免、可在 CI 执行的规则。

## 2. 用户价值

定义并执行分层、依赖、安全、数据、接口和部署架构规则。用于阻止循环依赖、越界访问、共享数据库和未鉴权接口。

## 3. 功能需求

| ID | 需求 |
|---|---|
| `REQ-27-01` | 内建规则覆盖分层、循环、服务调用、数据库归属、认证、敏感数据、依赖许可证。 |
| `REQ-27-02` | 规则版本与分析 run 绑定。 |
| `REQ-27-03` | 允许 dry-run 和历史回放。 |
| `REQ-27-04` | 规则性能需有预算。 |
| `REQ-27-05` | 修复建议与自动修改分离。 |

## 4. API 触点

- `/api/v1/architecture-rules`
- `/api/v1/rule-runs`
- `/api/v1/waivers`

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

- `architecture-rules.yaml`
- `rule-engine-report.json`

## 11. 任务清单

| Task | 标题 | 类型 | 优先级 |
|---|---|---|---|
| `ELMOS-PI-27-T01` | 定义 Rule DSL：scope、selector、condition、severity、evidence、exceptions | implementation | P2 |
| `ELMOS-PI-27-T02` | 实现内建规则与项目自定义规则 | implementation | P2 |
| `ELMOS-PI-27-T03` | 在全量和增量图谱上执行规则 | implementation | P2 |
| `ELMOS-PI-27-T04` | 为 violation 生成最短证据路径和修复建议 | implementation | P2 |
| `ELMOS-PI-27-T05` | 支持 waiver、到期时间、owner 和审批 | implementation | P2 |
| `ELMOS-PI-27-T06` | 集成 PR check、dashboard 和架构文档 | implementation | P2 |
| `ELMOS-PI-27-T07` | 实现权限、安全和不可信输入防护 | security | P2 |
| `ELMOS-PI-27-T08` | 接入日志、指标、Trace、错误分类和审计 | observability | P2 |
| `ELMOS-PI-27-T09` | 建立单元、契约、集成、E2E 与回归测试 | testing | P2 |
| `ELMOS-PI-27-T10` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P2 |

## 12. 验收标准

| ID | 验收标准 |
|---|---|
| `AC-27-01` | 规则 DSL 有 Schema 和单元测试。 |
| `AC-27-02` | 已知违规被稳定检测。 |
| `AC-27-03` | 例外到期后恢复失败。 |
| `AC-27-04` | CI 输出可定位到代码和路径。 |
| `AC-27-05` | 增量结果与全量结果一致。 |

## 13. 依赖

- `elmos-project-intelligence-graph`

## 14. 失败与恢复

- 将错误分类为 user-fixable、transient、capacity、permission、unsupported、internal。
- 可重试错误使用指数退避和最大次数；不可重试错误保留输入、日志和检查点。
- 恢复前验证 revision、配置、规则、模型、模板和权限是否仍兼容。
- 取消操作释放租约和临时资源，但保留审计与已确认 artifact。
