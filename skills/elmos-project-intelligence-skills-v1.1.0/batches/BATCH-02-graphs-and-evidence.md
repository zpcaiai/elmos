# BATCH-02-graphs-and-evidence — Code Graph、Project Intelligence Graph 与证据底座

## 目标

建立统一图谱和可追溯证据，使后续所有输出共享事实。

本批次必须交付可运行垂直切片，不接受只完成接口、空页面、TODO、伪数据或未执行测试。

## 前置条件

- `BATCH-01-ingestion-and-parsing` 已达到退出门禁。
- 已冻结目标分支/Commit，并记录工作区脏状态。
- 已建立本批次 checkpoint、回滚点、权限范围和系统 wall-clock ETA P50/P90。

## Skill 执行顺序

| 顺序 | Skill | 目标 | 直接依赖 |
|---:|---|---|---|
| 1 | `elmos-symbol-code-graph` | 把离散 Code IR 连接为可查询、可增量更新的 Code Graph。 | `elmos-multilanguage-parsing` |
| 2 | `elmos-evidence-provenance` | 让每个事实都可验证，明确区分 Confirmed、Inferred、Unknown 和 Recommended。 | `elmos-multilanguage-parsing` |
| 3 | `elmos-project-intelligence-graph` | 建立跨视角统一节点、关系、版本和查询接口，消除各生成器各自理解项目造成的不一致。 | `elmos-symbol-code-graph`, `elmos-evidence-provenance` |

## 实施任务

| Task | Skill | 标题 | 类型 | 优先级 |
|---|---|---|---|---|
| `ELMOS-PI-06-T01` | `elmos-symbol-code-graph` | 创建文件、模块、包、类型、函数和字段节点 | implementation | P0 |
| `ELMOS-PI-06-T02` | `elmos-symbol-code-graph` | 解析定义/引用、继承/实现、调用者/被调用者 | implementation | P0 |
| `ELMOS-PI-06-T03` | `elmos-symbol-code-graph` | 识别依赖注入、反射注册、路由绑定和 ORM 映射 | implementation | P0 |
| `ELMOS-PI-06-T04` | `elmos-symbol-code-graph` | 构建前端页面到 API、API 到服务、服务到数据库的跨层边 | implementation | P0 |
| `ELMOS-PI-06-T05` | `elmos-symbol-code-graph` | 为边保存解析策略、证据和置信度 | implementation | P0 |
| `ELMOS-PI-06-T06` | `elmos-symbol-code-graph` | 计算 SCC、中心性、扇入扇出和循环依赖 | implementation | P0 |
| `ELMOS-PI-06-T07` | `elmos-symbol-code-graph` | 实现权限、安全和不可信输入防护 | security | P0 |
| `ELMOS-PI-06-T08` | `elmos-symbol-code-graph` | 接入日志、指标、Trace、错误分类和审计 | observability | P0 |
| `ELMOS-PI-06-T09` | `elmos-symbol-code-graph` | 建立单元、契约、集成、E2E 与回归测试 | testing | P0 |
| `ELMOS-PI-06-T10` | `elmos-symbol-code-graph` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P0 |
| `ELMOS-PI-07-T01` | `elmos-project-intelligence-graph` | 定义统一节点和关系 taxonomy | implementation | P0 |
| `ELMOS-PI-07-T02` | `elmos-project-intelligence-graph` | 将代码节点聚合为模块、组件、服务、业务能力和部署单元 | implementation | P0 |
| `ELMOS-PI-07-T03` | `elmos-project-intelligence-graph` | 连接 API、事件、数据资产、测试、配置和安全边界 | implementation | P0 |
| `ELMOS-PI-07-T04` | `elmos-project-intelligence-graph` | 保存每个聚合结论的证据集合与置信度 | implementation | P0 |
| `ELMOS-PI-07-T05` | `elmos-project-intelligence-graph` | 提供 C4、流程、数据、功能、部署等投影视图 | implementation | P0 |
| `ELMOS-PI-07-T06` | `elmos-project-intelligence-graph` | 版本化图谱并支持 revision diff | implementation | P0 |
| `ELMOS-PI-07-T07` | `elmos-project-intelligence-graph` | 实现权限、安全和不可信输入防护 | security | P0 |
| `ELMOS-PI-07-T08` | `elmos-project-intelligence-graph` | 接入日志、指标、Trace、错误分类和审计 | observability | P0 |
| `ELMOS-PI-07-T09` | `elmos-project-intelligence-graph` | 建立单元、契约、集成、E2E 与回归测试 | testing | P0 |
| `ELMOS-PI-07-T10` | `elmos-project-intelligence-graph` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P0 |
| `ELMOS-PI-08-T01` | `elmos-evidence-provenance` | 定义 Evidence、Claim、Inference、Recommendation 数据模型 | implementation | P0 |
| `ELMOS-PI-08-T02` | `elmos-evidence-provenance` | 为文件行、AST、配置键、Trace span、测试结果生成稳定引用 | implementation | P0 |
| `ELMOS-PI-08-T03` | `elmos-evidence-provenance` | 按规则计算证据强度、冲突和新鲜度 | implementation | P0 |
| `ELMOS-PI-08-T04` | `elmos-evidence-provenance` | 将 claim 绑定到 artifact block、diagram node 和 slide element | implementation | P0 |
| `ELMOS-PI-08-T05` | `elmos-evidence-provenance` | 发现冲突时降级置信度并生成待确认任务 | implementation | P0 |
| `ELMOS-PI-08-T06` | `elmos-evidence-provenance` | 提供点击回源和批量证据导出 | implementation | P0 |
| `ELMOS-PI-08-T07` | `elmos-evidence-provenance` | 实现权限、安全和不可信输入防护 | security | P0 |
| `ELMOS-PI-08-T08` | `elmos-evidence-provenance` | 接入日志、指标、Trace、错误分类和审计 | observability | P0 |
| `ELMOS-PI-08-T09` | `elmos-evidence-provenance` | 建立单元、契约、集成、E2E 与回归测试 | testing | P0 |
| `ELMOS-PI-08-T10` | `elmos-evidence-provenance` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P0 |

## 预期交付物

- `code-graph-snapshot.json`（由 `elmos-symbol-code-graph` 负责）
- `unresolved-edges.json`（由 `elmos-symbol-code-graph` 负责）
- `evidence-bundle.json`（由 `elmos-evidence-provenance` 负责）
- `claim-register.json`（由 `elmos-evidence-provenance` 负责）
- `project-intelligence-graph.json`（由 `elmos-project-intelligence-graph` 负责）
- `graph-quality-report.json`（由 `elmos-project-intelligence-graph` 负责）
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
| `AC-06-01` | `elmos-symbol-code-graph` | Go to definition、find references 和 call hierarchy 在基准项目通过。 | required |
| `AC-06-02` | `elmos-symbol-code-graph` | 循环依赖检测与人工基线一致。 | required |
| `AC-06-03` | `elmos-symbol-code-graph` | 每条边可返回 evidence 与解析方法。 | required |
| `AC-06-04` | `elmos-symbol-code-graph` | 增量更新后无幽灵边。 | preferred |
| `AC-06-05` | `elmos-symbol-code-graph` | 图查询 p95 达到 SLO。 | preferred |
| `AC-07-01` | `elmos-project-intelligence-graph` | 同一事实在不同 artifact 中保持一致。 | required |
| `AC-07-02` | `elmos-project-intelligence-graph` | 任意图节点可回到代码或运行证据。 | required |
| `AC-07-03` | `elmos-project-intelligence-graph` | revision diff 能解释节点和边变化。 | required |
| `AC-07-04` | `elmos-project-intelligence-graph` | 人工 override 有审计和回滚。 | preferred |
| `AC-07-05` | `elmos-project-intelligence-graph` | 图质量指标可观测。 | preferred |
| `AC-08-01` | `elmos-evidence-provenance` | 随机抽取 claim 能定位到有效证据。 | required |
| `AC-08-02` | `elmos-evidence-provenance` | 代码移动后可通过 symbol/revision 重定位或明确失效。 | required |
| `AC-08-03` | `elmos-evidence-provenance` | 冲突证据不被静默选择。 | required |
| `AC-08-04` | `elmos-evidence-provenance` | 导出的证据包可离线验证哈希。 | preferred |
| `AC-08-05` | `elmos-evidence-provenance` | 所有生成器强制写 claim/evidence 关系。 | preferred |

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
