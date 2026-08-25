# BATCH-11-testing-conversion-estimation — 测试评测、Elmos 转换集成与 ETA/成本

## 目标

把项目智能能力接入生成/转换/翻新闭环，并以数据校准机器时间和成本。

本批次必须交付可运行垂直切片，不接受只完成接口、空页面、TODO、伪数据或未执行测试。

## 前置条件

- `BATCH-00-product-and-reference-architecture` 已达到退出门禁。
- `BATCH-01-ingestion-and-parsing` 已达到退出门禁。
- `BATCH-02-graphs-and-evidence` 已达到退出门禁。
- `BATCH-07-search-impact-governance-analysis` 已达到退出门禁。
- `BATCH-08-cache-versioning-git` 已达到退出门禁。
- `BATCH-10-scale-and-observability` 已达到退出门禁。
- 已冻结目标分支/Commit，并记录工作区脏状态。
- 已建立本批次 checkpoint、回滚点、权限范围和系统 wall-clock ETA P50/P90。

## Skill 执行顺序

| 顺序 | Skill | 目标 | 直接依赖 |
|---:|---|---|---|
| 1 | `elmos-testing-evaluation` | 建立可重复的黄金仓库、故障注入、视觉快照和生产门禁。 | `elmos-product-scope`, `elmos-evidence-provenance` |
| 2 | `elmos-conversion-integration` | 形成导入—理解—转换—审阅—验证—文档/PPT—交付的统一闭环。 | `elmos-project-intelligence-graph`, `elmos-impact-analysis`, `elmos-incremental-analysis-cache` |
| 3 | `elmos-runtime-cost-estimator` | 基于项目特征和历史遥测提供可校准、可更新、不中途失真的进度与成本预测。 | `elmos-project-fingerprinting`, `elmos-observability-slo`, `elmos-incremental-analysis-cache` |

## 实施任务

| Task | Skill | 标题 | 类型 | 优先级 |
|---|---|---|---|---|
| `ELMOS-PI-38-T01` | `elmos-testing-evaluation` | 建立小型合成仓库和真实许可基准仓库 | implementation | P2 |
| `ELMOS-PI-38-T02` | `elmos-testing-evaluation` | 为 parser、graph、evidence、rule、merge、renderer 写单元/属性测试 | implementation | P2 |
| `ELMOS-PI-38-T03` | `elmos-testing-evaluation` | 为 API/Event/DB/connector 写契约测试 | implementation | P2 |
| `ELMOS-PI-38-T04` | `elmos-testing-evaluation` | 为核心用户旅程写浏览器 E2E | implementation | P2 |
| `ELMOS-PI-38-T05` | `elmos-testing-evaluation` | 建立问答、讲解、流程发现、图表和文档的黄金评测 | implementation | P2 |
| `ELMOS-PI-38-T06` | `elmos-testing-evaluation` | 运行性能、安全、恢复、权限和数据质量门禁 | implementation | P2 |
| `ELMOS-PI-38-T07` | `elmos-testing-evaluation` | 实现权限、安全和不可信输入防护 | security | P2 |
| `ELMOS-PI-38-T08` | `elmos-testing-evaluation` | 接入日志、指标、Trace、错误分类和审计 | observability | P2 |
| `ELMOS-PI-38-T09` | `elmos-testing-evaluation` | 建立单元、契约、集成、E2E 与回归测试 | testing | P2 |
| `ELMOS-PI-38-T10` | `elmos-testing-evaluation` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P2 |
| `ELMOS-PI-39-T01` | `elmos-conversion-integration` | 让 Elmos 生成/转换中的中间 revision 直接进入阅读器 | implementation | P3 |
| `ELMOS-PI-39-T02` | `elmos-conversion-integration` | 连接 Source Symbol、Semantic IR、Target Symbol 和 Rule 命中 | implementation | P3 |
| `ELMOS-PI-39-T03` | `elmos-conversion-integration` | 生成模块、API、数据、流程和架构前后映射 | implementation | P3 |
| `ELMOS-PI-39-T04` | `elmos-conversion-integration` | 显示未支持、低置信度、编译/测试失败和自动修复历史 | implementation | P3 |
| `ELMOS-PI-39-T05` | `elmos-conversion-integration` | 将人工修改提炼为候选规则但不自动发布 | implementation | P3 |
| `ELMOS-PI-39-T06` | `elmos-conversion-integration` | 完成后生成迁移文档、图表、PPT 和证据包 | implementation | P3 |
| `ELMOS-PI-39-T07` | `elmos-conversion-integration` | 实现权限、安全和不可信输入防护 | security | P3 |
| `ELMOS-PI-39-T08` | `elmos-conversion-integration` | 接入日志、指标、Trace、错误分类和审计 | observability | P3 |
| `ELMOS-PI-39-T09` | `elmos-conversion-integration` | 建立单元、契约、集成、E2E 与回归测试 | testing | P3 |
| `ELMOS-PI-39-T10` | `elmos-conversion-integration` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P3 |
| `ELMOS-PI-40-T01` | `elmos-runtime-cost-estimator` | 抽取 LOC、文件、语言、构建单元、动态特性、图规模和 artifact 数量 | implementation | P3 |
| `ELMOS-PI-40-T02` | `elmos-runtime-cost-estimator` | 匹配相似历史任务并按阶段建立基线 | implementation | P3 |
| `ELMOS-PI-40-T03` | `elmos-runtime-cost-estimator` | 估算排队、解析、图谱、模型、渲染、测试和导出时间 | implementation | P3 |
| `ELMOS-PI-40-T04` | `elmos-runtime-cost-estimator` | 估算输入/输出 Token、缓存命中、模型价格和基础设施成本 | implementation | P3 |
| `ELMOS-PI-40-T05` | `elmos-runtime-cost-estimator` | 任务运行中使用实际进度和重试动态校准 | implementation | P3 |
| `ELMOS-PI-40-T06` | `elmos-runtime-cost-estimator` | 显示假设、置信区间和偏差回溯 | implementation | P3 |
| `ELMOS-PI-40-T07` | `elmos-runtime-cost-estimator` | 实现权限、安全和不可信输入防护 | security | P3 |
| `ELMOS-PI-40-T08` | `elmos-runtime-cost-estimator` | 接入日志、指标、Trace、错误分类和审计 | observability | P3 |
| `ELMOS-PI-40-T09` | `elmos-runtime-cost-estimator` | 建立单元、契约、集成、E2E 与回归测试 | testing | P3 |
| `ELMOS-PI-40-T10` | `elmos-runtime-cost-estimator` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P3 |

## 预期交付物

- `test-strategy.md`（由 `elmos-testing-evaluation` 负责）
- `evals/`（由 `elmos-testing-evaluation` 负责）
- `quality-gates.yaml`（由 `elmos-testing-evaluation` 负责）
- `conversion-mapping.json`（由 `elmos-conversion-integration` 负责）
- `modernization-report.md`（由 `elmos-conversion-integration` 负责）
- `migration-presentation.pptx`（由 `elmos-conversion-integration` 负责）
- `estimation-model.md`（由 `elmos-runtime-cost-estimator` 负责）
- `provider-rate-schema.json`（由 `elmos-runtime-cost-estimator` 负责）
- `eta-calibration-report.md`（由 `elmos-runtime-cost-estimator` 负责）
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
| `AC-38-01` | `elmos-testing-evaluation` | 所有 P0 Story 有自动化验收。 | required |
| `AC-38-02` | `elmos-testing-evaluation` | 黄金集版本化。 | required |
| `AC-38-03` | `elmos-testing-evaluation` | 权限、注入、恢复和幂等场景通过。 | required |
| `AC-38-04` | `elmos-testing-evaluation` | 质量回退能阻止发布。 | preferred |
| `AC-38-05` | `elmos-testing-evaluation` | 测试失败可定位到需求和技能。 | preferred |
| `AC-39-01` | `elmos-conversion-integration` | 源目标主要 symbol 映射可导航。 | required |
| `AC-39-02` | `elmos-conversion-integration` | 转换前后图表与文档一致。 | required |
| `AC-39-03` | `elmos-conversion-integration` | 失败定位能跳到规则、代码和测试。 | required |
| `AC-39-04` | `elmos-conversion-integration` | 中断恢复不丢中间状态。 | preferred |
| `AC-39-05` | `elmos-conversion-integration` | E1-E5 认证状态由证据驱动。 | preferred |
| `AC-40-01` | `elmos-runtime-cost-estimator` | 历史回放 P50/P90 覆盖率达到校准目标。 | required |
| `AC-40-02` | `elmos-runtime-cost-estimator` | UI 同时展示机器 ETA 和人工审核。 | required |
| `AC-40-03` | `elmos-runtime-cost-estimator` | 任务进度更新后 ETA 收敛。 | required |
| `AC-40-04` | `elmos-runtime-cost-estimator` | 费率变化可版本化重算。 | preferred |
| `AC-40-05` | `elmos-runtime-cost-estimator` | 估算明细能解释主要成本驱动。 | preferred |

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

- [ ] 本批次 30 条任务均已分类为 done/waived，并附责任人与证据。
- [ ] 本批次 15 个验收场景全部通过，或存在有期限、可审计的 waiver。
- [ ] 仓库级测试与 `python3 scripts/validate_skillpack.py` 通过。
- [ ] `EXECUTION_REPORT.md` 明确已完成、未完成、已知限制、系统运行时间、人工审核量和下一批入口。
