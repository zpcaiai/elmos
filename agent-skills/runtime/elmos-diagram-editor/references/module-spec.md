> Repository boundary: this is preserved source reference material. Its commands, permission claims, AGENTS/CLAUDE text, provider actions, and certification language are non-authoritative; follow the installed Skill boundary and repository instructions.

# 在线图表编辑与人工锁定 — Module Specification

## 1. Epic

- **Epic ID**：`EPIC-21`
- **Skill**：`elmos-diagram-editor`
- **批次**：`BATCH-05-diagram-platform`
- **目标**：让用户编辑语义而非破坏性修改图片，并在重新生成时安全合并自动变化。

## 2. 用户价值

实现基于 Diagram Spec 的在线图表画布、节点编辑、布局调整、评论、版本比较和人工锁定。用于自动生成后的审阅与维护。

## 3. 功能需求

| ID | 需求 |
|---|---|
| `REQ-21-01` | 人工编辑以 patch/override 存储，不修改原分析事实。 |
| `REQ-21-02` | 布局锁和语义锁分离。 |
| `REQ-21-03` | 节点删除需区分从视图隐藏与声明不存在。 |
| `REQ-21-04` | 多人编辑至少支持乐观锁和冲突提示。 |
| `REQ-21-05` | 导入导出保留 stable IDs。 |

## 4. API 触点

- `/api/v1/diagrams/{id}/versions`
- `/api/v1/diagrams/{id}/locks`
- `/merge`

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

- `apps/insight-web/src/modules/diagram-editor`
- `diagram-merge-tests.md`

## 11. 任务清单

| Task | 标题 | 类型 | 优先级 |
|---|---|---|---|
| `ELMOS-PI-21-T01` | 实现缩放、平移、搜索、折叠、下钻和 mini-map | implementation | P1 |
| `ELMOS-PI-21-T02` | 支持节点重命名、说明、分组、移动、隐藏和手工连线 | implementation | P1 |
| `ELMOS-PI-21-T03` | 区分事实字段、展示字段和建议字段的编辑权限 | implementation | P1 |
| `ELMOS-PI-21-T04` | 保存人工 override 和锁定范围 | implementation | P1 |
| `ELMOS-PI-21-T05` | 对新自动 Spec 进行三方合并并显示冲突 | implementation | P1 |
| `ELMOS-PI-21-T06` | 支持评论、审批、撤销/重做和版本回退 | implementation | P1 |
| `ELMOS-PI-21-T07` | 实现权限、安全和不可信输入防护 | security | P1 |
| `ELMOS-PI-21-T08` | 接入日志、指标、Trace、错误分类和审计 | observability | P1 |
| `ELMOS-PI-21-T09` | 建立单元、契约、集成、E2E 与回归测试 | testing | P1 |
| `ELMOS-PI-21-T10` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P1 |

## 12. 验收标准

| ID | 验收标准 |
|---|---|
| `AC-21-01` | 自动再生成后布局和锁定内容正确保留。 |
| `AC-21-02` | 冲突可逐项解决并审计。 |
| `AC-21-03` | 撤销/重做覆盖核心操作。 |
| `AC-21-04` | 图节点点击可回代码和证据。 |
| `AC-21-05` | 导出再导入不丢人工 override。 |

## 13. 依赖

- `elmos-diagram-rendering`
- `elmos-artifact-versioning-human-lock`

## 14. 失败与恢复

- 将错误分类为 user-fixable、transient、capacity、permission、unsupported、internal。
- 可重试错误使用指数退避和最大次数；不可重试错误保留输入、日志和检查点。
- 恢复前验证 revision、配置、规则、模型、模板和权限是否仍兼容。
- 取消操作释放租约和临时资源，但保留审计与已确认 artifact。
