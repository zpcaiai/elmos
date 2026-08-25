# 项目介绍与技术汇报 PPT 生成 — Module Specification

## 1. Epic

- **Epic ID**：`EPIC-23`
- **Skill**：`elmos-presentation-generation`
- **批次**：`BATCH-06-documents-presentations-reports`
- **目标**：把统一项目事实、图表和指标转为针对受众的可编辑演示文稿，并保留证据和演讲备注。

## 2. 用户价值

生成管理层项目介绍、技术评审、新人培训、售前、技术尽调、迁移翻新和生产认证 PPTX。用于可编辑、品牌化、可增量更新的演示材料。

## 3. 功能需求

| ID | 需求 |
|---|---|
| `REQ-23-01` | 支持 10/20/30 页与管理/技术/产品/客户受众。 |
| `REQ-23-02` | 使用 PPTX 原生可编辑对象；复杂图至少保留 SVG 和源 Spec。 |
| `REQ-23-03` | 每页记录 revision、claim IDs、generator version。 |
| `REQ-23-04` | 可生成中文、英文、双语和演讲备注。 |
| `REQ-23-05` | 支持企业 Logo、字体替代、页脚和保密级别。 |

## 4. API 触点

- `/api/v1/presentations/generate`
- `/api/v1/presentations/{id}/export`
- `/api/v1/slides/{id}/locks`

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

- `presentations/`
- `slide-manifest.json`
- `pptx-validation-report.md`

## 11. 任务清单

| Task | 标题 | 类型 | 优先级 |
|---|---|---|---|
| `ELMOS-PI-23-T01` | 选择演示类型并建立答案优先的故事线 | implementation | P1 |
| `ELMOS-PI-23-T02` | 为每页定义目的、主结论、证据、图表和备注 | implementation | P1 |
| `ELMOS-PI-23-T03` | 生成或复用架构图、流程图和指标图 | implementation | P1 |
| `ELMOS-PI-23-T04` | 使用模板引擎创建可编辑文本、形状、表格和图表 | implementation | P1 |
| `ELMOS-PI-23-T05` | 检查溢出、可读性、引用、品牌和敏感信息 | implementation | P1 |
| `ELMOS-PI-23-T06` | 按 slide stable ID 支持增量更新和人工锁定 | implementation | P1 |
| `ELMOS-PI-23-T07` | 实现权限、安全和不可信输入防护 | security | P1 |
| `ELMOS-PI-23-T08` | 接入日志、指标、Trace、错误分类和审计 | observability | P1 |
| `ELMOS-PI-23-T09` | 建立单元、契约、集成、E2E 与回归测试 | testing | P1 |
| `ELMOS-PI-23-T10` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P1 |

## 12. 验收标准

| ID | 验收标准 |
|---|---|
| `AC-23-01` | 所有文本无溢出且核心页面可编辑。 |
| `AC-23-02` | 关键结论有 evidence map。 |
| `AC-23-03` | 相同模板重生成能保留锁定页。 |
| `AC-23-04` | 不同受众故事线显著不同。 |
| `AC-23-05` | PPTX 可被主流 Office 软件正常打开。 |

## 13. 依赖

- `elmos-architecture-documentation`
- `elmos-diagram-rendering`

## 14. 失败与恢复

- 将错误分类为 user-fixable、transient、capacity、permission、unsupported、internal。
- 可重试错误使用指数退避和最大次数；不可重试错误保留输入、日志和检查点。
- 恢复前验证 revision、配置、规则、模型、模板和权限是否仍兼容。
- 取消操作释放租约和临时资源，但保留审计与已确认 artifact。
