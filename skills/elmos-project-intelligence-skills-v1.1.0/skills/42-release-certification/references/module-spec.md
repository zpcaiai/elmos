# 生产验收与 E1–E5 认证 — Module Specification

## 1. Epic

- **Epic ID**：`EPIC-42`
- **Skill**：`elmos-release-certification`
- **批次**：`BATCH-12-deployment-and-certification`
- **目标**：用证据驱动的门禁决定是否可试用、可团队使用、可生产或可关键业务部署。

## 2. 用户价值

汇总功能、质量、性能、安全、恢复、证据和运营结果，执行 Elmos Project Intelligence Studio 或项目转换输出的分级生产认证。

## 3. 功能需求

| ID | 需求 |
|---|---|
| `REQ-42-01` | 严重安全、数据隔离、恢复和证据缺失为硬门禁。 |
| `REQ-42-02` | 认证标准版本化。 |
| `REQ-42-03` | 每项标准关联自动测试或人工审批。 |
| `REQ-42-04` | 不同部署模式可有附加控制但不能降低核心安全。 |
| `REQ-42-05` | 认证结果在 UI、报告和 API 一致。 |

## 4. API 触点

- `/api/v1/certifications`
- `/api/v1/certifications/{id}/evidence`
- `/sign`

所有 API 必须：

- 使用 `/api/v1` 版本前缀或清晰的内部契约版本；
- 携带 `tenant_id`、`project_id`、`revision_id/analysis_run_id` 的服务端上下文；
- 支持幂等键、分页、错误码和权限校验；
- 不在错误消息中泄露代码、凭据或跨租户对象；
- 对长任务返回 `job_id`、状态、检查点和可恢复错误。

## 5. 主要领域实体

- `TestCase`
- `EvalDataset`
- `QualityGate`
- `CertificationEvidence`

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

- 自动化验收覆盖率
- 评测回退数
- 发布门禁通过率

## 10. 交付物

- `certification-matrix.yaml`
- `certification-report.md`
- `signed-evidence-bundle.zip`

## 11. 任务清单

| Task | 标题 | 类型 | 优先级 |
|---|---|---|---|
| `ELMOS-PI-42-T01` | 定义 E1 原型、E2 可验证、E3 团队级、E4 生产级、E5 关键业务级标准 | implementation | P3 |
| `ELMOS-PI-42-T02` | 收集构建、测试、评测、性能、安全、权限、恢复和文档证据 | implementation | P3 |
| `ELMOS-PI-42-T03` | 验证证据新鲜度、revision、环境和完整性 | implementation | P3 |
| `ELMOS-PI-42-T04` | 执行硬门禁与可审批 waiver | implementation | P3 |
| `ELMOS-PI-42-T05` | 生成失败项、修复任务、残余风险和重新认证范围 | implementation | P3 |
| `ELMOS-PI-42-T06` | 冻结并签名认证报告 | implementation | P3 |
| `ELMOS-PI-42-T07` | 实现权限、安全和不可信输入防护 | security | P3 |
| `ELMOS-PI-42-T08` | 接入日志、指标、Trace、错误分类和审计 | observability | P3 |
| `ELMOS-PI-42-T09` | 建立单元、契约、集成、E2E 与回归测试 | testing | P3 |
| `ELMOS-PI-42-T10` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P3 |

## 12. 验收标准

| ID | 验收标准 |
|---|---|
| `AC-42-01` | 所有门禁有明确证据。 |
| `AC-42-02` | 失败可生成可执行修复 backlog。 |
| `AC-42-03` | 签名包可离线验证。 |
| `AC-42-04` | 认证状态变更有职责分离与审计。 |
| `AC-42-05` | E4/E5 通过灾备和安全红队。 |

## 13. 依赖

- `elmos-testing-evaluation`
- `elmos-security-threat-model`
- `elmos-deployment-private-cloud`

## 14. 失败与恢复

- 将错误分类为 user-fixable、transient、capacity、permission、unsupported、internal。
- 可重试错误使用指数退避和最大次数；不可重试错误保留输入、日志和检查点。
- 恢复前验证 revision、配置、规则、模型、模板和权限是否仍兼容。
- 取消操作释放租约和临时资源，但保留审计与已确认 artifact。
