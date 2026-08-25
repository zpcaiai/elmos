# 多格式图表生成与渲染 — Module Specification

## 1. Epic

- **Epic ID**：`EPIC-20`
- **Skill**：`elmos-diagram-rendering`
- **批次**：`BATCH-05-diagram-platform`
- **目标**：提供一致、清晰、可缩放、可缓存且可回源的自动图表输出。

## 2. 用户价值

把 Diagram Spec 渲染为 Mermaid、PlantUML、Structurizr、Graphviz、BPMN XML、Markmap、SVG、PNG、PDF 和可嵌入组件。

## 3. 功能需求

| ID | 需求 |
|---|---|
| `REQ-20-01` | 文本不得被截断且支持中英文。 |
| `REQ-20-02` | SVG 必须消毒，禁止脚本和外部资源。 |
| `REQ-20-03` | 渲染失败返回可定位到节点/边的诊断。 |
| `REQ-20-04` | 导出结果记录 renderer/version/font substitution。 |
| `REQ-20-05` | 大图提供交互式 Web 视图而非强行单页。 |

## 4. API 触点

- `/api/v1/diagrams/render`
- `/api/v1/diagrams/{id}/exports`

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

- `services/diagram-renderer`
- `render-compatibility-matrix.md`

## 11. 任务清单

| Task | 标题 | 类型 | 优先级 |
|---|---|---|---|
| `ELMOS-PI-20-T01` | 选择适合图类型的渲染器并生成中间 DSL | implementation | P1 |
| `ELMOS-PI-20-T02` | 使用 ELK/Dagre/Graphviz 等执行自动布局 | implementation | P1 |
| `ELMOS-PI-20-T03` | 对大图进行聚合、分层、分页和 overview+detail | implementation | P1 |
| `ELMOS-PI-20-T04` | 嵌入 element ID、evidence link 和 accessibility metadata | implementation | P1 |
| `ELMOS-PI-20-T05` | 沙箱化渲染进程并限制 CPU/内存/时间 | implementation | P1 |
| `ELMOS-PI-20-T06` | 缓存 spec hash + renderer version + theme 的结果 | implementation | P1 |
| `ELMOS-PI-20-T07` | 实现权限、安全和不可信输入防护 | security | P1 |
| `ELMOS-PI-20-T08` | 接入日志、指标、Trace、错误分类和审计 | observability | P1 |
| `ELMOS-PI-20-T09` | 建立单元、契约、集成、E2E 与回归测试 | testing | P1 |
| `ELMOS-PI-20-T10` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P1 |

## 12. 验收标准

| ID | 验收标准 |
|---|---|
| `AC-20-01` | 核心图表快照测试通过。 |
| `AC-20-02` | 1000 节点压力图有受控降级且不 OOM。 |
| `AC-20-03` | SVG 中 element ID 与 Spec 一致。 |
| `AC-20-04` | 同版本确定性渲染达到目标。 |
| `AC-20-05` | 恶意 DSL 安全测试通过。 |

## 13. 依赖

- `elmos-diagram-spec-engine`

## 14. 失败与恢复

- 将错误分类为 user-fixable、transient、capacity、permission、unsupported、internal。
- 可重试错误使用指数退避和最大次数；不可重试错误保留输入、日志和检查点。
- 恢复前验证 revision、配置、规则、模型、模板和权限是否仍兼容。
- 取消操作释放租约和临时资源，但保留审计与已确认 artifact。
