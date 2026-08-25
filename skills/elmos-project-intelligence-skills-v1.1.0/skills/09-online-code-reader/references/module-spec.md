# 在线代码阅读器 — Module Specification

## 1. Epic

- **Epic ID**：`EPIC-09`
- **Skill**：`elmos-online-code-reader`
- **批次**：`BATCH-03-code-reader-and-explanation`
- **目标**：提供快速、安全、可扩展的项目代码阅读入口，并与架构、流程、数据和转换结果双向联动。

## 2. 用户价值

实现以阅读和证据导航为核心的浏览器代码工作台。用于文件树、代码查看、Diff、书签、评论和跨视图联动；不等同于完整通用在线 IDE。

## 3. 功能需求

| ID | 需求 |
|---|---|
| `REQ-09-01` | 首屏不得等待整个项目分析完成。 |
| `REQ-09-02` | 文件内容分块/流式加载，支持大文件和二进制预览策略。 |
| `REQ-09-03` | URL 可复制并固定 revision，避免链接漂移。 |
| `REQ-09-04` | 源代码只读为默认；编辑能力单独授权。 |
| `REQ-09-05` | 图表节点、文档引用和问答答案能定位到精确行。 |

## 4. API 触点

- `/api/v1/files`
- `/api/v1/files/{id}/content`
- `/api/v1/diffs`
- `/api/v1/bookmarks`

所有 API 必须：

- 使用 `/api/v1` 版本前缀或清晰的内部契约版本；
- 携带 `tenant_id`、`project_id`、`revision_id/analysis_run_id` 的服务端上下文；
- 支持幂等键、分页、错误码和权限校验；
- 不在错误消息中泄露代码、凭据或跨租户对象；
- 对长任务返回 `job_id`、状态、检查点和可恢复错误。

## 5. 主要领域实体

- `ReaderSession`
- `Bookmark`
- `Comment`
- `Explanation`
- `LearningPath`

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

- 代码打开 p95
- 导航准确率
- 讲解引用正确率
- 学习路径完成率

## 10. 交付物

- `apps/insight-web/src/modules/code-reader`
- `code-reader-e2e-report.md`

## 11. 任务清单

| Task | 标题 | 类型 | 优先级 |
|---|---|---|---|
| `ELMOS-PI-09-T01` | 建立项目/仓库/分支/Commit 选择器和虚拟化文件树 | implementation | P0 |
| `ELMOS-PI-09-T02` | 接入 Monaco，支持高亮、折叠、大纲、面包屑、多标签和分屏 | implementation | P0 |
| `ELMOS-PI-09-T03` | 实现原始/目标、Commit/Commit、自动/人工修改 Diff | implementation | P0 |
| `ELMOS-PI-09-T04` | 实现深链：文件、行、Symbol、Claim、Diagram Node | implementation | P0 |
| `ELMOS-PI-09-T05` | 加入书签、私人笔记、团队评论、最近阅读和收藏 | implementation | P0 |
| `ELMOS-PI-09-T06` | 接入权限、脱敏、审计和大文件降级 | implementation | P0 |
| `ELMOS-PI-09-T07` | 实现权限、安全和不可信输入防护 | security | P0 |
| `ELMOS-PI-09-T08` | 接入日志、指标、Trace、错误分类和审计 | observability | P0 |
| `ELMOS-PI-09-T09` | 建立单元、契约、集成、E2E 与回归测试 | testing | P0 |
| `ELMOS-PI-09-T10` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P0 |

## 12. 验收标准

| ID | 验收标准 |
|---|---|
| `AC-09-01` | 100k 文件项目文件树可交互且不冻结。 |
| `AC-09-02` | 代码打开、标签切换和定位达到体验 SLO。 |
| `AC-09-03` | 复制的深链在同权限用户下可复现。 |
| `AC-09-04` | Diff 能区分自动生成、人工编辑和转换来源。 |
| `AC-09-05` | 权限撤销后缓存内容不可继续访问。 |

## 13. 依赖

- `elmos-repository-ingestion`
- `elmos-symbol-code-graph`

## 14. 失败与恢复

- 将错误分类为 user-fixable、transient、capacity、permission、unsupported、internal。
- 可重试错误使用指数退避和最大次数；不可重试错误保留输入、日志和检查点。
- 恢复前验证 revision、配置、规则、模型、模板和权限是否仍兼容。
- 取消操作释放租约和临时资源，但保留审计与已确认 artifact。

## 15. 在线调试联动

- 提供“从当前方法/测试/流程创建 Debug Session”入口；
- 入口只提交 revision/symbol/test refs，不直接传递仓库凭据；
- 调试能力缺失时显示安装/权限/Runtime Profile 原因；
- 当前执行行、Frame 与副作用可回链代码阅读器。
