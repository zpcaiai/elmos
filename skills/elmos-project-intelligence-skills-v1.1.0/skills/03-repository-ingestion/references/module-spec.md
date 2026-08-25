# 仓库接入与修订冻结 — Module Specification

## 1. Epic

- **Epic ID**：`EPIC-03`
- **Skill**：`elmos-repository-ingestion`
- **批次**：`BATCH-01-ingestion-and-parsing`
- **目标**：把任意受支持项目转换为不可歧义、可重放、可审计的 Project Revision。

## 2. 用户价值

实现 Git/ZIP/本地目录/多仓库项目的安全接入、修订冻结和内容清单。用于首次导入、同步、分支切换和 Elmos 临时项目接入。

## 3. 功能需求

| ID | 需求 |
|---|---|
| `REQ-03-01` | 支持 GitHub、GitLab、Gitee、Bitbucket 与通用 Git。 |
| `REQ-03-02` | 凭据只通过 Secret Broker 获取且不得落入日志。 |
| `REQ-03-03` | 支持 include/exclude glob、最大文件和仓库配额。 |
| `REQ-03-04` | 重复导入相同内容必须命中内容寻址存储。 |
| `REQ-03-05` | 导入失败必须提供可修复分类。 |

## 4. API 触点

- `/api/v1/projects`
- `/api/v1/repositories/import`
- `/api/v1/revisions`

所有 API 必须：

- 使用 `/api/v1` 版本前缀或清晰的内部契约版本；
- 携带 `tenant_id`、`project_id`、`revision_id/analysis_run_id` 的服务端上下文；
- 支持幂等键、分页、错误码和权限校验；
- 不在错误消息中泄露代码、凭据或跨租户对象；
- 对长任务返回 `job_id`、状态、检查点和可恢复错误。

## 5. 主要领域实体

- `Project`
- `Repository`
- `Revision`
- `SourceBlob`
- `ImportAudit`

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

- 导入成功率
- 去重率
- 敏感信息泄漏事件数
- 指纹识别准确率

## 10. 交付物

- `project-manifest.json`
- `ingestion-report.json`

## 11. 任务清单

| Task | 标题 | 类型 | 优先级 |
|---|---|---|---|
| `ELMOS-PI-03-T01` | 校验来源、租户、权限和内容大小 | implementation | P0 |
| `ELMOS-PI-03-T02` | 解析 Git、子模块、LFS、Monorepo 和多仓库组合 | implementation | P0 |
| `ELMOS-PI-03-T03` | 冻结 commit SHA；上传包计算内容哈希 | implementation | P0 |
| `ELMOS-PI-03-T04` | 扫描文件类型、二进制、生成代码、Vendor 与敏感文件 | implementation | P0 |
| `ELMOS-PI-03-T05` | 写入对象存储并生成不可变 manifest | implementation | P0 |
| `ELMOS-PI-03-T06` | 发布 project.revision.ingested 事件 | implementation | P0 |
| `ELMOS-PI-03-T07` | 实现权限、安全和不可信输入防护 | security | P0 |
| `ELMOS-PI-03-T08` | 接入日志、指标、Trace、错误分类和审计 | observability | P0 |
| `ELMOS-PI-03-T09` | 建立单元、契约、集成、E2E 与回归测试 | testing | P0 |
| `ELMOS-PI-03-T10` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P0 |

## 12. 验收标准

| ID | 验收标准 |
|---|---|
| `AC-03-01` | 相同 revision 重复导入得到相同 manifest hash。 |
| `AC-03-02` | 断点续传不会产生重复对象。 |
| `AC-03-03` | 子模块 revision 被明确记录。 |
| `AC-03-04` | 私有凭据不出现在日志、事件或 artifact。 |
| `AC-03-05` | 删除项目后按保留策略可验证清除。 |

## 13. 依赖

- `elmos-reference-architecture`

## 14. 失败与恢复

- 将错误分类为 user-fixable、transient、capacity、permission、unsupported、internal。
- 可重试错误使用指数退避和最大次数；不可重试错误保留输入、日志和检查点。
- 恢复前验证 revision、配置、规则、模型、模板和权限是否仍兼容。
- 取消操作释放租约和临时资源，但保留审计与已确认 artifact。
