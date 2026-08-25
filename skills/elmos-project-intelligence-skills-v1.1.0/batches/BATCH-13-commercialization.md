# BATCH-13-commercialization — 商业版本、计量与交付套餐

## 目标

形成可售卖版本、配额、计量、账单事件、许可证和交付模板。

本批次必须交付可运行垂直切片，不接受只完成接口、空页面、TODO、伪数据或未执行测试。

## 前置条件

- `BATCH-11-testing-conversion-estimation` 已达到退出门禁。
- `BATCH-12-deployment-and-certification` 已达到退出门禁。
- 已冻结目标分支/Commit，并记录工作区脏状态。
- 已建立本批次 checkpoint、回滚点、权限范围和系统 wall-clock ETA P50/P90。

## Skill 执行顺序

| 顺序 | Skill | 目标 | 直接依赖 |
|---:|---|---|---|
| 1 | `elmos-commercial-packaging` | 把技术能力组合为可售卖、可运营、不会破坏核心可信度和安全性的商业产品。 | `elmos-runtime-cost-estimator`, `elmos-release-certification` |

## 实施任务

| Task | Skill | 标题 | 类型 | 优先级 |
|---|---|---|---|---|
| `ELMOS-PI-43-T01` | `elmos-commercial-packaging` | 定义个人开发者、团队、软件现代化服务商和大型企业场景 | implementation | P3 |
| `ELMOS-PI-43-T02` | `elmos-commercial-packaging` | 按代码规模、分析 run、模型 Token、artifact、并发和保留期设计计量 | implementation | P3 |
| `ELMOS-PI-43-T03` | `elmos-commercial-packaging` | 设计 Reader、Architecture、Documentation、Modernization 等套餐 | implementation | P3 |
| `ELMOS-PI-43-T04` | `elmos-commercial-packaging` | 区分 SaaS、专属租户、私有化和离线授权 | implementation | P3 |
| `ELMOS-PI-43-T05` | `elmos-commercial-packaging` | 定义试用、超额、预算告警、用量可视化和成本归因 | implementation | P3 |
| `ELMOS-PI-43-T06` | `elmos-commercial-packaging` | 生成售前材料、实施清单和 SLA 边界 | implementation | P3 |
| `ELMOS-PI-43-T07` | `elmos-commercial-packaging` | 实现权限、安全和不可信输入防护 | security | P3 |
| `ELMOS-PI-43-T08` | `elmos-commercial-packaging` | 接入日志、指标、Trace、错误分类和审计 | observability | P3 |
| `ELMOS-PI-43-T09` | `elmos-commercial-packaging` | 建立单元、契约、集成、E2E 与回归测试 | testing | P3 |
| `ELMOS-PI-43-T10` | `elmos-commercial-packaging` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P3 |

## 预期交付物

- `edition-matrix.md`（由 `elmos-commercial-packaging` 负责）
- `metering-event-schema.json`（由 `elmos-commercial-packaging` 负责）
- `commercial-model.md`（由 `elmos-commercial-packaging` 负责）
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
| `AC-43-01` | `elmos-commercial-packaging` | Edition matrix 无矛盾。 | required |
| `AC-43-02` | `elmos-commercial-packaging` | 计量与账单样例可对账。 | required |
| `AC-43-03` | `elmos-commercial-packaging` | 预算告警和硬限额测试通过。 | required |
| `AC-43-04` | `elmos-commercial-packaging` | 销售材料与真实实现/认证一致。 | preferred |
| `AC-43-05` | `elmos-commercial-packaging` | 单位经济模型能解释毛利主要驱动。 | preferred |

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

- [ ] 本批次 10 条任务均已分类为 done/waived，并附责任人与证据。
- [ ] 本批次 5 个验收场景全部通过，或存在有期限、可审计的 waiver。
- [ ] 仓库级测试与 `python3 scripts/validate_skillpack.py` 通过。
- [ ] `EXECUTION_REPORT.md` 明确已完成、未完成、已知限制、系统运行时间、人工审核量和下一批入口。
