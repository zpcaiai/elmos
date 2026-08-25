# BATCH-10-scale-and-observability — 大型仓库扩展与运营可观测性

## 目标

验证百万行、多仓库场景，并建立 SLO、指标、Trace 和容量治理。

本批次必须交付可运行垂直切片，不接受只完成接口、空页面、TODO、伪数据或未执行测试。

## 前置条件

- `BATCH-00-product-and-reference-architecture` 已达到退出门禁。
- `BATCH-01-ingestion-and-parsing` 已达到退出门禁。
- `BATCH-08-cache-versioning-git` 已达到退出门禁。
- 已冻结目标分支/Commit，并记录工作区脏状态。
- 已建立本批次 checkpoint、回滚点、权限范围和系统 wall-clock ETA P50/P90。

## Skill 执行顺序

| 顺序 | Skill | 目标 | 直接依赖 |
|---:|---|---|---|
| 1 | `elmos-large-repository-scaling` | 在资源预算内处理大型项目，并提供渐进可用、可恢复和可预测的机器执行 ETA。 | `elmos-incremental-analysis-cache`, `elmos-project-fingerprinting` |
| 2 | `elmos-observability-slo` | 让质量、性能、成本、队列、失败、证据覆盖和用户体验可测量。 | `elmos-reference-architecture` |

## 实施任务

| Task | Skill | 标题 | 类型 | 优先级 |
|---|---|---|---|---|
| `ELMOS-PI-36-T01` | `elmos-large-repository-scaling` | 按仓库、模块、语言、构建单元和内容哈希分片 | implementation | P2 |
| `ELMOS-PI-36-T02` | `elmos-large-repository-scaling` | 定义优先索引：manifest→入口→高价值模块→全量 | implementation | P2 |
| `ELMOS-PI-36-T03` | `elmos-large-repository-scaling` | 并行解析但串行提交一致图谱版本 | implementation | P2 |
| `ELMOS-PI-36-T04` | `elmos-large-repository-scaling` | 对图查询实施分页、限制、近似和预计算 | implementation | P2 |
| `ELMOS-PI-36-T05` | `elmos-large-repository-scaling` | 控制模型上下文、批处理、缓存和并发配额 | implementation | P2 |
| `ELMOS-PI-36-T06` | `elmos-large-repository-scaling` | 执行 S/M/L/XL 仓库压测和故障注入 | implementation | P2 |
| `ELMOS-PI-36-T07` | `elmos-large-repository-scaling` | 实现权限、安全和不可信输入防护 | security | P2 |
| `ELMOS-PI-36-T08` | `elmos-large-repository-scaling` | 接入日志、指标、Trace、错误分类和审计 | observability | P2 |
| `ELMOS-PI-36-T09` | `elmos-large-repository-scaling` | 建立单元、契约、集成、E2E 与回归测试 | testing | P2 |
| `ELMOS-PI-36-T10` | `elmos-large-repository-scaling` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P2 |
| `ELMOS-PI-37-T01` | `elmos-observability-slo` | 定义服务和用户旅程级 SLI | implementation | P2 |
| `ELMOS-PI-37-T02` | `elmos-observability-slo` | 统一 trace_id、job_id、project_id、analysis_run_id、artifact_id | implementation | P2 |
| `ELMOS-PI-37-T03` | `elmos-observability-slo` | 记录队列、阶段时长、重试、缓存、Token、模型、渲染和图查询指标 | implementation | P2 |
| `ELMOS-PI-37-T04` | `elmos-observability-slo` | 记录质量指标：解析率、图完整度、引用正确率、stale 率 | implementation | P2 |
| `ELMOS-PI-37-T05` | `elmos-observability-slo` | 建立 SLO、错误预算、告警和 Runbook | implementation | P2 |
| `ELMOS-PI-37-T06` | `elmos-observability-slo` | 实现敏感字段过滤与日志采样 | implementation | P2 |
| `ELMOS-PI-37-T07` | `elmos-observability-slo` | 实现权限、安全和不可信输入防护 | security | P2 |
| `ELMOS-PI-37-T08` | `elmos-observability-slo` | 接入日志、指标、Trace、错误分类和审计 | observability | P2 |
| `ELMOS-PI-37-T09` | `elmos-observability-slo` | 建立单元、契约、集成、E2E 与回归测试 | testing | P2 |
| `ELMOS-PI-37-T10` | `elmos-observability-slo` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P2 |

## 预期交付物

- `capacity-model.md`（由 `elmos-large-repository-scaling` 负责）
- `load-test-scenarios.yaml`（由 `elmos-large-repository-scaling` 负责）
- `scaling-report.md`（由 `elmos-large-repository-scaling` 负责）
- `observability-spec.md`（由 `elmos-observability-slo` 负责）
- `slo-catalog.yaml`（由 `elmos-observability-slo` 负责）
- `runbooks/`（由 `elmos-observability-slo` 负责）
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
| `AC-36-01` | `elmos-large-repository-scaling` | 目标规模压测达到吞吐和内存预算。 | required |
| `AC-36-02` | `elmos-large-repository-scaling` | 部分失败可重试单 shard。 | required |
| `AC-36-03` | `elmos-large-repository-scaling` | 增量 1% 变更成本显著低于全量。 | required |
| `AC-36-04` | `elmos-large-repository-scaling` | 公平调度避免大项目饿死小项目。 | preferred |
| `AC-36-05` | `elmos-large-repository-scaling` | ETA 校准误差有持续监控。 | preferred |
| `AC-37-01` | `elmos-observability-slo` | 关键请求可端到端 Trace。 | required |
| `AC-37-02` | `elmos-observability-slo` | 告警通过演练。 | required |
| `AC-37-03` | `elmos-observability-slo` | 仪表盘能定位慢阶段和成本来源。 | required |
| `AC-37-04` | `elmos-observability-slo` | 日志脱敏测试通过。 | preferred |
| `AC-37-05` | `elmos-observability-slo` | SLO 报告可按租户和版本比较。 | preferred |

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
