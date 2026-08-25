# BATCH-09-collaboration-and-connectors — 协作治理、权限与连接器

## 目标

支持企业团队协作、审批、审计及外部系统/MCP 集成。

本批次必须交付可运行垂直切片，不接受只完成接口、空页面、TODO、伪数据或未执行测试。

## 前置条件

- `BATCH-00-product-and-reference-architecture` 已达到退出门禁。
- `BATCH-01-ingestion-and-parsing` 已达到退出门禁。
- `BATCH-07-search-impact-governance-analysis` 已达到退出门禁。
- 已冻结目标分支/Commit，并记录工作区脏状态。
- 已建立本批次 checkpoint、回滚点、权限范围和系统 wall-clock ETA P50/P90。

## Skill 执行顺序

| 顺序 | Skill | 目标 | 直接依赖 |
|---:|---|---|---|
| 1 | `elmos-collaboration-governance` | 提供最小权限、可委派、可审计的多角色协作体验。 | `elmos-reference-architecture`, `elmos-security-threat-model` |
| 2 | `elmos-integrations-mcp` | 让 Elmos 接入外部系统而不把供应商逻辑耦合到分析核心。 | `elmos-repository-ingestion`, `elmos-collaboration-governance` |

## 实施任务

| Task | Skill | 标题 | 类型 | 优先级 |
|---|---|---|---|---|
| `ELMOS-PI-34-T01` | `elmos-collaboration-governance` | 定义管理员、架构师、开发、测试、运维、安全、产品、访客、客户、审计等角色 | implementation | P2 |
| `ELMOS-PI-34-T02` | `elmos-collaboration-governance` | 细化 project/repo/revision/file/artifact/claim/export/model 权限 | implementation | P2 |
| `ELMOS-PI-34-T03` | `elmos-collaboration-governance` | 实现评论、@、任务、订阅、审批和通知 | implementation | P2 |
| `ELMOS-PI-34-T04` | `elmos-collaboration-governance` | 实现带有效期、水印、范围和撤销的分享 | implementation | P2 |
| `ELMOS-PI-34-T05` | `elmos-collaboration-governance` | 为读取、搜索、生成、导出、修改和认证记录审计 | implementation | P2 |
| `ELMOS-PI-34-T06` | `elmos-collaboration-governance` | 接入 SSO、SCIM、MFA 与组织策略 | implementation | P2 |
| `ELMOS-PI-34-T07` | `elmos-collaboration-governance` | 实现权限、安全和不可信输入防护 | security | P2 |
| `ELMOS-PI-34-T08` | `elmos-collaboration-governance` | 接入日志、指标、Trace、错误分类和审计 | observability | P2 |
| `ELMOS-PI-34-T09` | `elmos-collaboration-governance` | 建立单元、契约、集成、E2E 与回归测试 | testing | P2 |
| `ELMOS-PI-34-T10` | `elmos-collaboration-governance` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P2 |
| `ELMOS-PI-35-T01` | `elmos-integrations-mcp` | 定义 Repository、Issue、Docs、CI、Trace、Artifact Registry 等 Port | implementation | P2 |
| `ELMOS-PI-35-T02` | `elmos-integrations-mcp` | 为供应商实现 Adapter 和能力发现 | implementation | P2 |
| `ELMOS-PI-35-T03` | `elmos-integrations-mcp` | 使用 OAuth/OIDC/service account/short-lived token | implementation | P2 |
| `ELMOS-PI-35-T04` | `elmos-integrations-mcp` | 为读取、搜索、写入、回调定义精确工具 Schema | implementation | P2 |
| `ELMOS-PI-35-T05` | `elmos-integrations-mcp` | 实现限流、重试、幂等、游标同步和健康检查 | implementation | P2 |
| `ELMOS-PI-35-T06` | `elmos-integrations-mcp` | 为连接器建立权限、审计、数据驻留和故障降级 | implementation | P2 |
| `ELMOS-PI-35-T07` | `elmos-integrations-mcp` | 实现权限、安全和不可信输入防护 | security | P2 |
| `ELMOS-PI-35-T08` | `elmos-integrations-mcp` | 接入日志、指标、Trace、错误分类和审计 | observability | P2 |
| `ELMOS-PI-35-T09` | `elmos-integrations-mcp` | 建立单元、契约、集成、E2E 与回归测试 | testing | P2 |
| `ELMOS-PI-35-T10` | `elmos-integrations-mcp` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P2 |

## 预期交付物

- `rbac-matrix.csv`（由 `elmos-collaboration-governance` 负责）
- `audit-event-schema.json`（由 `elmos-collaboration-governance` 负责）
- `governance-tests.md`（由 `elmos-collaboration-governance` 负责）
- `connector-sdk.md`（由 `elmos-integrations-mcp` 负责）
- `mcp-tool-catalog.yaml`（由 `elmos-integrations-mcp` 负责）
- `connector-contract-tests.md`（由 `elmos-integrations-mcp` 负责）
- 本批次 `EXECUTION_REPORT.md`、测试结果、审计日志引用和恢复 checkpoint。
- 更新后的需求—实现—测试—证据追踪矩阵。

## 端到端实现步骤

1. 扫描现有仓库，建立“已存在/缺失/冲突/可复用”差距清单。
2. 冻结 API、事件、Schema、领域实体和权限矩阵；兼容性变更必须有迁移方案。
3. 先完成最小真实数据垂直切片，再补异常、恢复、配额和多租户路径。
4. 为长任务实现幂等、暂停、恢复、重试、取消、租约和检查点。
5. 接入日志、指标、Trace、错误分类、审计和 evidence binding。
6. 执行单元、契约、集成、E2E、安全、性能/恢复测试中的适用集合。
7. 回放失败场景，修复至本批次全部硬门禁通过。
8. 固化机器 wall-clock 实测、Token/计算/存储消耗和人工审核工作量。

## 验收场景

| AC | Skill | 验收结果 | 自动化 |
|---|---|---|---|
| `AC-34-01` | `elmos-collaboration-governance` | 权限矩阵自动测试覆盖允许与拒绝。 | required |
| `AC-34-02` | `elmos-collaboration-governance` | 撤销后分享和缓存访问失效。 | required |
| `AC-34-03` | `elmos-collaboration-governance` | 跨租户查询红队无泄漏。 | required |
| `AC-34-04` | `elmos-collaboration-governance` | 审批职责分离生效。 | preferred |
| `AC-34-05` | `elmos-collaboration-governance` | 审计事件包含 who/what/when/where/result。 | preferred |
| `AC-35-01` | `elmos-integrations-mcp` | 至少一个 Git 和一个 Trace 连接器端到端通过。 | required |
| `AC-35-02` | `elmos-integrations-mcp` | 限流/过期 token/部分失败可恢复。 | required |
| `AC-35-03` | `elmos-integrations-mcp` | 工具 Schema 通过契约测试。 | required |
| `AC-35-04` | `elmos-integrations-mcp` | 写操作幂等。 | preferred |
| `AC-35-05` | `elmos-integrations-mcp` | 连接器可替换而不改分析核心。 | preferred |

## 生产门禁

- [ ] 所有 P0/P1 任务均有真实实现、迁移和测试；无 placeholder-only 完成项。
- [ ] 固定 revision 重跑结果可复现，输出绑定生成器、规则、模板和模型版本。
- [ ] Confirmed claim 可深链至证据；Inferred/Unknown/Recommended 标识正确。
- [ ] 多租户、最小权限、Prompt Injection、Secrets、日志脱敏和不可信内容测试通过。
- [ ] Worker 中断、重复消息、超时、取消和恢复不造成重复副作用。
- [ ] API/事件/Schema 有版本，兼容性与回滚方案已验证。
- [ ] UI 显示 revision、覆盖率、可信度、新鲜度、阶段、机器 ETA P50/P90 和恢复入口。
- [ ] 所有人工锁定内容、评论、审批与审计记录在再生成后保持。

## 检查点与恢复

每个阶段记录 `checkpoint_id`、输入 manifest、revision、已提交副作用、缓存键、工具/模型版本和下一步。恢复前验证这些条件仍兼容；不兼容时创建新 run，不覆盖旧证据。

## 退出标准

- [ ] 本批次 20 条任务均已分类为 done/waived，并附责任人与证据。
- [ ] 本批次 10 个验收场景全部通过，或存在有期限、可审计的 waiver。
- [ ] 仓库级测试与 `python3 scripts/validate_skillpack.py` 通过。
- [ ] `EXECUTION_REPORT.md` 明确已完成、未完成、已知限制、系统运行时间、人工审核量和下一批入口。
