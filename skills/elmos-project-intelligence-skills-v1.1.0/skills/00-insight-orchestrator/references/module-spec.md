# Project Intelligence Studio 总编排 — Module Specification

## 1. Epic

- **Epic ID**：`EPIC-00`
- **Skill**：`elmos-insight-orchestrator`
- **批次**：`BATCH-00-product-and-reference-architecture`
- **目标**：把代码阅读、架构理解、流程发现、图表、文档、PPT、问答、影响分析和 Elmos 转换能力组织为可暂停、可恢复、可验证的统一工作流。

## 2. 用户价值

规划、实施或验收 Elmos Project Intelligence Studio 全链路能力。用于跨多个子系统的复杂任务、批次推进、依赖协调和最终生产认证；不要用于只修改单个局部组件。

## 3. 功能需求

| ID | 需求 |
|---|---|
| `REQ-00-01` | 长任务必须支持幂等、暂停、恢复、重试、取消与检查点。 |
| `REQ-00-02` | 所有生成结论必须可追踪到代码、配置、Schema、测试或运行证据。 |
| `REQ-00-03` | 不同 artifact 必须共享同一 Project Intelligence Graph 和 Evidence Graph。 |
| `REQ-00-04` | 系统运行时间使用机器 wall-clock P50/P90；人工审核时间单独列示。 |
| `REQ-00-05` | 不得用演示数据冒充真实项目分析结果。 |

## 4. API 触点

- `/api/v1/jobs`
- `/api/v1/jobs/{id}/pause`
- `/resume`
- `/cancel`
- `/checkpoints`

所有 API 必须：

- 使用 `/api/v1` 版本前缀或清晰的内部契约版本；
- 携带 `tenant_id`、`project_id`、`revision_id/analysis_run_id` 的服务端上下文；
- 支持幂等键、分页、错误码和权限校验；
- 不在错误消息中泄露代码、凭据或跨租户对象；
- 对长任务返回 `job_id`、状态、检查点和可恢复错误。

## 5. 主要领域实体

- `ExecutionPlan`
- `Job`
- `Checkpoint`
- `EvidenceBundle`

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

- 批次完成率
- 恢复成功率
- 重复副作用数
- 证据完整率

## 10. 交付物

- `IMPLEMENTATION_PLAN.md`
- `EXECUTION_REPORT.md`
- `evidence-bundle.json`

## 11. 任务清单

| Task | 标题 | 类型 | 优先级 |
|---|---|---|---|
| `ELMOS-PI-00-T01` | 读取 AGENTS.md、CLAUDE.md、skillpack.yaml 和当前仓库状态 | implementation | P0 |
| `ELMOS-PI-00-T02` | 识别请求涉及的能力域，选择最少且足够的子技能 | implementation | P0 |
| `ELMOS-PI-00-T03` | 建立可执行计划、依赖、风险、回滚点和完成定义 | implementation | P0 |
| `ELMOS-PI-00-T04` | 按检查点实施；每个阶段产出代码、测试、文档和证据 | implementation | P0 |
| `ELMOS-PI-00-T05` | 运行包级验证与目标仓库测试，修复失败 | implementation | P0 |
| `ELMOS-PI-00-T06` | 生成完成报告，列出已完成、未完成、已知限制和下一批入口 | implementation | P0 |
| `ELMOS-PI-00-T07` | 实现权限、安全和不可信输入防护 | security | P0 |
| `ELMOS-PI-00-T08` | 接入日志、指标、Trace、错误分类和审计 | observability | P0 |
| `ELMOS-PI-00-T09` | 建立单元、契约、集成、E2E 与回归测试 | testing | P0 |
| `ELMOS-PI-00-T10` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P0 |

## 12. 验收标准

| ID | 验收标准 |
|---|---|
| `AC-00-01` | 子技能选择与依赖正确且可解释。 |
| `AC-00-02` | 每个批次均有可运行测试和验收证据。 |
| `AC-00-03` | 任务中断后可从最近检查点恢复且不重复副作用。 |
| `AC-00-04` | 最终报告可追踪到 Commit、分析版本和 artifact 版本。 |
| `AC-00-05` | 全包验证脚本返回成功。 |

## 13. 依赖

- 无；可作为起始技能。

## 14. 失败与恢复

- 将错误分类为 user-fixable、transient、capacity、permission、unsupported、internal。
- 可重试错误使用指数退避和最大次数；不可重试错误保留输入、日志和检查点。
- 恢复前验证 revision、配置、规则、模型、模板和权限是否仍兼容。
- 取消操作释放租约和临时资源，但保留审计与已确认 artifact。
