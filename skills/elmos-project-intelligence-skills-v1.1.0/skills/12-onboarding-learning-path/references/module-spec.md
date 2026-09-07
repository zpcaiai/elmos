# 项目介绍与新人学习路径 — Module Specification

## 1. Epic

- **Epic ID**：`EPIC-12`
- **Skill**：`elmos-onboarding-learning-path`
- **批次**：`BATCH-03-code-reader-and-explanation`
- **目标**：把庞大代码库转换为角色化、可进度跟踪、可回源的学习路径。

## 2. 用户价值

根据角色生成项目概览、术语表、阅读顺序、核心流程和上手任务。用于新人入职、项目交接和跨团队理解。

## 3. 功能需求

| ID | 需求 |
|---|---|
| `REQ-12-01` | 路径应从系统上下文逐步深入，不从随机核心类开始。 |
| `REQ-12-02` | 标记必须理解、可选、危险修改区域。 |
| `REQ-12-03` | 术语映射业务名词、代码名、表名和 API。 |
| `REQ-12-04` | 学习材料绑定 revision。 |
| `REQ-12-05` | 可导出 Markdown、DOCX、PPT 大纲。 |

## 4. API 触点

- `/api/v1/onboarding/guides`
- `/api/v1/learning-paths`

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

- `onboarding-guide.md`
- `learning-path.json`

## 11. 任务清单

| Task | 标题 | 类型 | 优先级 |
|---|---|---|---|
| `ELMOS-PI-12-T01` | 识别项目使命、边界、核心业务能力和技术栈 | implementation | P1 |
| `ELMOS-PI-12-T02` | 为开发、测试、运维、产品、架构、安全设计不同路径 | implementation | P1 |
| `ELMOS-PI-12-T03` | 选择最具代表性的文件、调用链、流程和数据模型 | implementation | P1 |
| `ELMOS-PI-12-T04` | 生成 30 分钟、半天、3 天、2 周不同学习计划 | implementation | P1 |
| `ELMOS-PI-12-T05` | 为每阶段提供可验证任务和相关代码深链 | implementation | P1 |
| `ELMOS-PI-12-T06` | 根据用户反馈和项目变更更新路径 | implementation | P1 |
| `ELMOS-PI-12-T07` | 实现权限、安全和不可信输入防护 | security | P1 |
| `ELMOS-PI-12-T08` | 接入日志、指标、Trace、错误分类和审计 | observability | P1 |
| `ELMOS-PI-12-T09` | 建立单元、契约、集成、E2E 与回归测试 | testing | P1 |
| `ELMOS-PI-12-T10` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P1 |

## 12. 验收标准

| ID | 验收标准 |
|---|---|
| `AC-12-01` | 用户能沿路径定位并运行最小开发闭环。 |
| `AC-12-02` | 每个学习节点有目标、材料、练习和完成条件。 |
| `AC-12-03` | 路径中的文件和链接全部存在。 |
| `AC-12-04` | 项目变化后受影响节点被标记 stale。 |
| `AC-12-05` | 角色间内容明显差异化。 |

## 13. 依赖

- `elmos-code-explanation`
- `elmos-project-intelligence-graph`

## 14. 失败与恢复

- 将错误分类为 user-fixable、transient、capacity、permission、unsupported、internal。
- 可重试错误使用指数退避和最大次数；不可重试错误保留输入、日志和检查点。
- 恢复前验证 revision、配置、规则、模型、模板和权限是否仍兼容。
- 取消操作释放租约和临时资源，但保留审计与已确认 artifact。
