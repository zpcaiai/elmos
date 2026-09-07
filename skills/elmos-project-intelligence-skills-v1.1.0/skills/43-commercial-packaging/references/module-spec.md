# 商业版本、计量与交付套餐 — Module Specification

## 1. Epic

- **Epic ID**：`EPIC-43`
- **Skill**：`elmos-commercial-packaging`
- **批次**：`BATCH-13-commercialization`
- **目标**：把技术能力组合为可售卖、可运营、不会破坏核心可信度和安全性的商业产品。

## 2. 用户价值

设计 Elmos Project Intelligence Studio 的 Community/Professional/Enterprise/Private 等版本、用量计量、配额、计费、试用和交付边界。

## 3. 功能需求

| ID | 需求 |
|---|---|
| `REQ-43-01` | 核心证据、权限和安全不得作为付费后才启用的可选正确性。 |
| `REQ-43-02` | 定价假设与实际基础设施/模型成本联动。 |
| `REQ-43-03` | 企业功能覆盖 SSO、审计、私有模型、驻留和支持。 |
| `REQ-43-04` | 版本能力通过 entitlement service 控制并可审计。 |
| `REQ-43-05` | 计量事件幂等且可对账。 |

## 4. API 触点

- `/api/v1/entitlements`
- `/api/v1/usage`
- `/api/v1/quotas`
- `/api/v1/budgets`

所有 API 必须：

- 使用 `/api/v1` 版本前缀或清晰的内部契约版本；
- 携带 `tenant_id`、`project_id`、`revision_id/analysis_run_id` 的服务端上下文；
- 支持幂等键、分页、错误码和权限校验；
- 不在错误消息中泄露代码、凭据或跨租户对象；
- 对长任务返回 `job_id`、状态、检查点和可恢复错误。

## 5. 主要领域实体

- `Edition`
- `Entitlement`
- `UsageEvent`
- `Quota`
- `Budget`

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

- 试用转化率
- 单位任务毛利
- 配额告警准确率
- 账单对账差异

## 10. 交付物

- `edition-matrix.md`
- `metering-event-schema.json`
- `commercial-model.md`

## 11. 任务清单

| Task | 标题 | 类型 | 优先级 |
|---|---|---|---|
| `ELMOS-PI-43-T01` | 定义个人开发者、团队、软件现代化服务商和大型企业场景 | implementation | P3 |
| `ELMOS-PI-43-T02` | 按代码规模、分析 run、模型 Token、artifact、并发和保留期设计计量 | implementation | P3 |
| `ELMOS-PI-43-T03` | 设计 Reader、Architecture、Documentation、Modernization 等套餐 | implementation | P3 |
| `ELMOS-PI-43-T04` | 区分 SaaS、专属租户、私有化和离线授权 | implementation | P3 |
| `ELMOS-PI-43-T05` | 定义试用、超额、预算告警、用量可视化和成本归因 | implementation | P3 |
| `ELMOS-PI-43-T06` | 生成售前材料、实施清单和 SLA 边界 | implementation | P3 |
| `ELMOS-PI-43-T07` | 实现权限、安全和不可信输入防护 | security | P3 |
| `ELMOS-PI-43-T08` | 接入日志、指标、Trace、错误分类和审计 | observability | P3 |
| `ELMOS-PI-43-T09` | 建立单元、契约、集成、E2E 与回归测试 | testing | P3 |
| `ELMOS-PI-43-T10` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P3 |

## 12. 验收标准

| ID | 验收标准 |
|---|---|
| `AC-43-01` | Edition matrix 无矛盾。 |
| `AC-43-02` | 计量与账单样例可对账。 |
| `AC-43-03` | 预算告警和硬限额测试通过。 |
| `AC-43-04` | 销售材料与真实实现/认证一致。 |
| `AC-43-05` | 单位经济模型能解释毛利主要驱动。 |

## 13. 依赖

- `elmos-runtime-cost-estimator`
- `elmos-release-certification`

## 14. 失败与恢复

- 将错误分类为 user-fixable、transient、capacity、permission、unsupported、internal。
- 可重试错误使用指数退避和最大次数；不可重试错误保留输入、日志和检查点。
- 恢复前验证 revision、配置、规则、模型、模板和权限是否仍兼容。
- 取消操作释放租约和临时资源，但保留审计与已确认 artifact。
