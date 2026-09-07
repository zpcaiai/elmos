# BATCH-00-product-and-reference-architecture — 产品基线与参考架构

## 目标

冻结产品范围、用户旅程、系统边界、技术原则和可验收基线。

本批次必须交付可运行垂直切片，不接受只完成接口、空页面、TODO、伪数据或未执行测试。

## 前置条件

- 已读取当前 Elmos 仓库、现有 AGENTS/CLAUDE 指令、技术栈与部署约束。
- 已冻结目标分支/Commit，并记录工作区脏状态。
- 已建立本批次 checkpoint、回滚点、权限范围和系统 wall-clock ETA P50/P90。

## Skill 执行顺序

| 顺序 | Skill | 目标 | 直接依赖 |
|---:|---|---|---|
| 1 | `elmos-insight-orchestrator` | 把代码阅读、架构理解、流程发现、图表、文档、PPT、问答、影响分析和 Elmos 转换能力组织为可暂停、可恢复、可验证的统一工作流。 | 无 |
| 2 | `elmos-product-scope` | 把模糊产品想法转化为有角色、有场景、有边界、有验收指标的生产级需求基线。 | 无 |
| 3 | `elmos-reference-architecture` | 建立可扩展、可替换、可私有化部署的参考架构，避免 UI、分析引擎、模型和存储相互耦合。 | `elmos-product-scope` |

## 实施任务

| Task | Skill | 标题 | 类型 | 优先级 |
|---|---|---|---|---|
| `ELMOS-PI-00-T01` | `elmos-insight-orchestrator` | 读取 AGENTS.md、CLAUDE.md、skillpack.yaml 和当前仓库状态 | implementation | P0 |
| `ELMOS-PI-00-T02` | `elmos-insight-orchestrator` | 识别请求涉及的能力域，选择最少且足够的子技能 | implementation | P0 |
| `ELMOS-PI-00-T03` | `elmos-insight-orchestrator` | 建立可执行计划、依赖、风险、回滚点和完成定义 | implementation | P0 |
| `ELMOS-PI-00-T04` | `elmos-insight-orchestrator` | 按检查点实施；每个阶段产出代码、测试、文档和证据 | implementation | P0 |
| `ELMOS-PI-00-T05` | `elmos-insight-orchestrator` | 运行包级验证与目标仓库测试，修复失败 | implementation | P0 |
| `ELMOS-PI-00-T06` | `elmos-insight-orchestrator` | 生成完成报告，列出已完成、未完成、已知限制和下一批入口 | implementation | P0 |
| `ELMOS-PI-00-T07` | `elmos-insight-orchestrator` | 实现权限、安全和不可信输入防护 | security | P0 |
| `ELMOS-PI-00-T08` | `elmos-insight-orchestrator` | 接入日志、指标、Trace、错误分类和审计 | observability | P0 |
| `ELMOS-PI-00-T09` | `elmos-insight-orchestrator` | 建立单元、契约、集成、E2E 与回归测试 | testing | P0 |
| `ELMOS-PI-00-T10` | `elmos-insight-orchestrator` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P0 |
| `ELMOS-PI-01-T01` | `elmos-product-scope` | 识别用户角色、核心任务和痛点 | implementation | P0 |
| `ELMOS-PI-01-T02` | `elmos-product-scope` | 将能力拆为 Read、Explain、Explore、Flow、Diagram、Document、Present、Impact | implementation | P0 |
| `ELMOS-PI-01-T03` | `elmos-product-scope` | 定义每项能力的输入、输出、异常、权限和数据保留 | implementation | P0 |
| `ELMOS-PI-01-T04` | `elmos-product-scope` | 按 P0-P3 排序并标注依赖 | implementation | P0 |
| `ELMOS-PI-01-T05` | `elmos-product-scope` | 为每个 Story 编写可自动验证的完成条件 | implementation | P0 |
| `ELMOS-PI-01-T06` | `elmos-product-scope` | 建立需求到技能、API、数据表和测试的追踪关系 | implementation | P0 |
| `ELMOS-PI-01-T07` | `elmos-product-scope` | 实现权限、安全和不可信输入防护 | security | P0 |
| `ELMOS-PI-01-T08` | `elmos-product-scope` | 接入日志、指标、Trace、错误分类和审计 | observability | P0 |
| `ELMOS-PI-01-T09` | `elmos-product-scope` | 建立单元、契约、集成、E2E 与回归测试 | testing | P0 |
| `ELMOS-PI-01-T10` | `elmos-product-scope` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P0 |
| `ELMOS-PI-02-T01` | `elmos-reference-architecture` | 定义 Browser、Control Plane、Analysis Plane、Artifact Plane 和 Storage Plane | implementation | P0 |
| `ELMOS-PI-02-T02` | `elmos-reference-architecture` | 划分前端、项目 API、解析索引、图谱、AI 编排、渲染、导出和工作流服务 | implementation | P0 |
| `ELMOS-PI-02-T03` | `elmos-reference-architecture` | 定义 PostgreSQL、图数据库、对象存储、搜索、缓存的职责和替换接口 | implementation | P0 |
| `ELMOS-PI-02-T04` | `elmos-reference-architecture` | 定义 Temporal 工作流、事件总线和幂等键 | implementation | P0 |
| `ELMOS-PI-02-T05` | `elmos-reference-architecture` | 定义多租户、网络边界、Secrets Broker 和审计 | implementation | P0 |
| `ELMOS-PI-02-T06` | `elmos-reference-architecture` | 生成当前/目标架构图和 ADR | implementation | P0 |
| `ELMOS-PI-02-T07` | `elmos-reference-architecture` | 实现权限、安全和不可信输入防护 | security | P0 |
| `ELMOS-PI-02-T08` | `elmos-reference-architecture` | 接入日志、指标、Trace、错误分类和审计 | observability | P0 |
| `ELMOS-PI-02-T09` | `elmos-reference-architecture` | 建立单元、契约、集成、E2E 与回归测试 | testing | P0 |
| `ELMOS-PI-02-T10` | `elmos-reference-architecture` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P0 |

## 预期交付物

- `IMPLEMENTATION_PLAN.md`（由 `elmos-insight-orchestrator` 负责）
- `EXECUTION_REPORT.md`（由 `elmos-insight-orchestrator` 负责）
- `evidence-bundle.json`（由 `elmos-insight-orchestrator` 负责）
- `docs/01-product-requirements.md`（由 `elmos-product-scope` 负责）
- `backlog/epics.yaml`（由 `elmos-product-scope` 负责）
- `backlog/traceability.csv`（由 `elmos-product-scope` 负责）
- `docs/02-reference-architecture.md`（由 `elmos-reference-architecture` 负责）
- `docs/adr/`（由 `elmos-reference-architecture` 负责）
- `diagrams/reference-architecture.yaml`（由 `elmos-reference-architecture` 负责）
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
| `AC-00-01` | `elmos-insight-orchestrator` | 子技能选择与依赖正确且可解释。 | required |
| `AC-00-02` | `elmos-insight-orchestrator` | 每个批次均有可运行测试和验收证据。 | required |
| `AC-00-03` | `elmos-insight-orchestrator` | 任务中断后可从最近检查点恢复且不重复副作用。 | required |
| `AC-00-04` | `elmos-insight-orchestrator` | 最终报告可追踪到 Commit、分析版本和 artifact 版本。 | preferred |
| `AC-00-05` | `elmos-insight-orchestrator` | 全包验证脚本返回成功。 | preferred |
| `AC-01-01` | `elmos-product-scope` | 每个 Epic 至少关联一个用户角色、一个 API/界面和一个验收场景。 | required |
| `AC-01-02` | `elmos-product-scope` | P0 能独立形成从导入仓库到可证据化输出的闭环。 | required |
| `AC-01-03` | `elmos-product-scope` | 范围外清单明确，能防止在线 IDE 范围失控。 | required |
| `AC-01-04` | `elmos-product-scope` | 需求编号可在 backlog、测试和文档中追踪。 | preferred |
| `AC-02-01` | `elmos-reference-architecture` | 服务边界无循环部署依赖。 | required |
| `AC-02-02` | `elmos-reference-architecture` | 每个持久化数据类型有唯一主责存储。 | required |
| `AC-02-03` | `elmos-reference-architecture` | 任何 worker 重启后工作流可恢复。 | required |
| `AC-02-04` | `elmos-reference-architecture` | 架构支持 SaaS、单租户私有化和离线受限部署。 | preferred |
| `AC-02-05` | `elmos-reference-architecture` | ADR 记录关键替代方案及弃用原因。 | preferred |

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
- [ ] 本批次 14 个验收场景全部通过，或存在有期限、可审计的 waiver。
- [ ] 仓库级测试与 `python3 scripts/validate_skillpack.py` 通过。
- [ ] `EXECUTION_REPORT.md` 明确已完成、未完成、已知限制、系统运行时间、人工审核量和下一批入口。
