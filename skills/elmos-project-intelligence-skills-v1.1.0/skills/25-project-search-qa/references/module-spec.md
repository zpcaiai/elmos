# 项目全局搜索与证据化问答 — Module Specification

## 1. Epic

- **Epic ID**：`EPIC-25`
- **Skill**：`elmos-project-search-qa`
- **批次**：`BATCH-07-search-impact-governance-analysis`
- **目标**：以最小充分上下文回答项目问题，返回文件、行号、路径、图表、置信度和未知项。

## 2. 用户价值

提供符号、文本、结构、图谱和语义混合搜索，以及基于项目证据的自然语言问答。用于查找实现、数据来源、风险和修改位置。

## 3. 功能需求

| ID | 需求 |
|---|---|
| `REQ-25-01` | 支持精准短问、复杂多跳问和源/目标项目对比。 |
| `REQ-25-02` | 答案固定 revision，必要时显示当前分支变化。 |
| `REQ-25-03` | 引用格式可由 UI 点击回代码。 |
| `REQ-25-04` | 大问题可生成可恢复分析任务。 |
| `REQ-25-05` | Prompt/检索/模型版本可审计。 |

## 4. API 触点

- `/api/v1/search`
- `/api/v1/qa`
- `/api/v1/qa/{id}/feedback`

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

- `qa-api.yaml`
- `qa-evaluation-dataset.jsonl`
- `qa-eval-report.md`

## 11. 任务清单

| Task | 标题 | 类型 | 优先级 |
|---|---|---|---|
| `ELMOS-PI-25-T01` | 分类问题为导航、解释、架构、流程、数据、影响、风险或比较 | implementation | P2 |
| `ELMOS-PI-25-T02` | 执行 lexical、symbol、structural、graph 和 vector 混合检索 | implementation | P2 |
| `ELMOS-PI-25-T03` | 重排并验证结果的新鲜度、revision 和权限 | implementation | P2 |
| `ELMOS-PI-25-T04` | 先构建证据表，再生成答案 | implementation | P2 |
| `ELMOS-PI-25-T05` | 返回直接答案、证据、置信度、未确认项和相关视图 | implementation | P2 |
| `ELMOS-PI-25-T06` | 记录匿名化评测信号和用户纠错 | implementation | P2 |
| `ELMOS-PI-25-T07` | 实现权限、安全和不可信输入防护 | security | P2 |
| `ELMOS-PI-25-T08` | 接入日志、指标、Trace、错误分类和审计 | observability | P2 |
| `ELMOS-PI-25-T09` | 建立单元、契约、集成、E2E 与回归测试 | testing | P2 |
| `ELMOS-PI-25-T10` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P2 |

## 12. 验收标准

| ID | 验收标准 |
|---|---|
| `AC-25-01` | 黄金问题集准确率、引用正确率和无回答准确率达到目标。 |
| `AC-25-02` | 跨多跳路径问题可返回完整路径。 |
| `AC-25-03` | 权限与 prompt injection 红队通过。 |
| `AC-25-04` | 过期索引有清晰提示。 |
| `AC-25-05` | 用户纠错可进入评测而非直接改写事实。 |

## 13. 依赖

- `elmos-project-intelligence-graph`
- `elmos-evidence-provenance`

## 14. 失败与恢复

- 将错误分类为 user-fixable、transient、capacity、permission、unsupported、internal。
- 可重试错误使用指数退避和最大次数；不可重试错误保留输入、日志和检查点。
- 恢复前验证 revision、配置、规则、模型、模板和权限是否仍兼容。
- 取消操作释放租约和临时资源，但保留审计与已确认 artifact。
