# BATCH-07-search-impact-governance-analysis — 项目问答、影响、规则、漂移、风险与安全

## 目标

交付面向决策的项目智能分析与治理闭环。

本批次必须交付可运行垂直切片，不接受只完成接口、空页面、TODO、伪数据或未执行测试。

## 前置条件

- `BATCH-02-graphs-and-evidence` 已达到退出门禁。
- `BATCH-04-architecture-flow-data` 已达到退出门禁。
- 已冻结目标分支/Commit，并记录工作区脏状态。
- 已建立本批次 checkpoint、回滚点、权限范围和系统 wall-clock ETA P50/P90。

## Skill 执行顺序

| 顺序 | Skill | 目标 | 直接依赖 |
|---:|---|---|---|
| 1 | `elmos-project-search-qa` | 以最小充分上下文回答项目问题，返回文件、行号、路径、图表、置信度和未知项。 | `elmos-project-intelligence-graph`, `elmos-evidence-provenance` |
| 2 | `elmos-impact-analysis` | 生成可解释的影响半径、风险等级、受影响 artifact 和最小回归测试建议。 | `elmos-project-intelligence-graph`, `elmos-runtime-trace-fusion` |
| 3 | `elmos-architecture-rules` | 将架构原则转为可版本化、可测试、可豁免、可在 CI 执行的规则。 | `elmos-project-intelligence-graph` |
| 4 | `elmos-architecture-drift` | 持续发现实际系统偏离架构意图的位置，并驱动评审、文档更新和改造任务。 | `elmos-architecture-discovery`, `elmos-runtime-trace-fusion`, `elmos-architecture-rules` |
| 5 | `elmos-risk-technical-debt` | 生成可证据化、可排序、可行动的风险和现代化优先级，而非泛泛代码评价。 | `elmos-project-intelligence-graph`, `elmos-impact-analysis` |
| 6 | `elmos-security-threat-model` | 把安全证据嵌入项目图谱、代码阅读、文档和认证流程。 | `elmos-data-architecture-lineage`, `elmos-api-event-topology`, `elmos-architecture-rules` |

## 实施任务

| Task | Skill | 标题 | 类型 | 优先级 |
|---|---|---|---|---|
| `ELMOS-PI-25-T01` | `elmos-project-search-qa` | 分类问题为导航、解释、架构、流程、数据、影响、风险或比较 | implementation | P2 |
| `ELMOS-PI-25-T02` | `elmos-project-search-qa` | 执行 lexical、symbol、structural、graph 和 vector 混合检索 | implementation | P2 |
| `ELMOS-PI-25-T03` | `elmos-project-search-qa` | 重排并验证结果的新鲜度、revision 和权限 | implementation | P2 |
| `ELMOS-PI-25-T04` | `elmos-project-search-qa` | 先构建证据表，再生成答案 | implementation | P2 |
| `ELMOS-PI-25-T05` | `elmos-project-search-qa` | 返回直接答案、证据、置信度、未确认项和相关视图 | implementation | P2 |
| `ELMOS-PI-25-T06` | `elmos-project-search-qa` | 记录匿名化评测信号和用户纠错 | implementation | P2 |
| `ELMOS-PI-25-T07` | `elmos-project-search-qa` | 实现权限、安全和不可信输入防护 | security | P2 |
| `ELMOS-PI-25-T08` | `elmos-project-search-qa` | 接入日志、指标、Trace、错误分类和审计 | observability | P2 |
| `ELMOS-PI-25-T09` | `elmos-project-search-qa` | 建立单元、契约、集成、E2E 与回归测试 | testing | P2 |
| `ELMOS-PI-25-T10` | `elmos-project-search-qa` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P2 |
| `ELMOS-PI-26-T01` | `elmos-impact-analysis` | 解析变更 symbol、契约、Schema、配置和部署资源 | implementation | P2 |
| `ELMOS-PI-26-T02` | `elmos-impact-analysis` | 沿调用、数据、事件、部署和功能关系传播影响 | implementation | P2 |
| `ELMOS-PI-26-T03` | `elmos-impact-analysis` | 应用深度、边类型、置信度和运行热度权重 | implementation | P2 |
| `ELMOS-PI-26-T04` | `elmos-impact-analysis` | 识别 breaking change、数据迁移和安全边界变化 | implementation | P2 |
| `ELMOS-PI-26-T05` | `elmos-impact-analysis` | 选择相关测试、文档、图表和 PPT 页面 | implementation | P2 |
| `ELMOS-PI-26-T06` | `elmos-impact-analysis` | 输出确定、可能、未知影响及理由 | implementation | P2 |
| `ELMOS-PI-26-T07` | `elmos-impact-analysis` | 实现权限、安全和不可信输入防护 | security | P2 |
| `ELMOS-PI-26-T08` | `elmos-impact-analysis` | 接入日志、指标、Trace、错误分类和审计 | observability | P2 |
| `ELMOS-PI-26-T09` | `elmos-impact-analysis` | 建立单元、契约、集成、E2E 与回归测试 | testing | P2 |
| `ELMOS-PI-26-T10` | `elmos-impact-analysis` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P2 |
| `ELMOS-PI-27-T01` | `elmos-architecture-rules` | 定义 Rule DSL：scope、selector、condition、severity、evidence、exceptions | implementation | P2 |
| `ELMOS-PI-27-T02` | `elmos-architecture-rules` | 实现内建规则与项目自定义规则 | implementation | P2 |
| `ELMOS-PI-27-T03` | `elmos-architecture-rules` | 在全量和增量图谱上执行规则 | implementation | P2 |
| `ELMOS-PI-27-T04` | `elmos-architecture-rules` | 为 violation 生成最短证据路径和修复建议 | implementation | P2 |
| `ELMOS-PI-27-T05` | `elmos-architecture-rules` | 支持 waiver、到期时间、owner 和审批 | implementation | P2 |
| `ELMOS-PI-27-T06` | `elmos-architecture-rules` | 集成 PR check、dashboard 和架构文档 | implementation | P2 |
| `ELMOS-PI-27-T07` | `elmos-architecture-rules` | 实现权限、安全和不可信输入防护 | security | P2 |
| `ELMOS-PI-27-T08` | `elmos-architecture-rules` | 接入日志、指标、Trace、错误分类和审计 | observability | P2 |
| `ELMOS-PI-27-T09` | `elmos-architecture-rules` | 建立单元、契约、集成、E2E 与回归测试 | testing | P2 |
| `ELMOS-PI-27-T10` | `elmos-architecture-rules` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P2 |
| `ELMOS-PI-28-T01` | `elmos-architecture-drift` | 规范化设计、静态和运行模型到统一语义 | implementation | P2 |
| `ELMOS-PI-28-T02` | `elmos-architecture-drift` | 比较节点、关系、属性、所有权和安全边界 | implementation | P2 |
| `ELMOS-PI-28-T03` | `elmos-architecture-drift` | 分类 expected change、undocumented change、violation、observation gap | implementation | P2 |
| `ELMOS-PI-28-T04` | `elmos-architecture-drift` | 计算影响和严重度 | implementation | P2 |
| `ELMOS-PI-28-T05` | `elmos-architecture-drift` | 生成图表 diff、证据和建议动作 | implementation | P2 |
| `ELMOS-PI-28-T06` | `elmos-architecture-drift` | 支持确认、接受为新设计、拒绝或创建修复任务 | implementation | P2 |
| `ELMOS-PI-28-T07` | `elmos-architecture-drift` | 实现权限、安全和不可信输入防护 | security | P2 |
| `ELMOS-PI-28-T08` | `elmos-architecture-drift` | 接入日志、指标、Trace、错误分类和审计 | observability | P2 |
| `ELMOS-PI-28-T09` | `elmos-architecture-drift` | 建立单元、契约、集成、E2E 与回归测试 | testing | P2 |
| `ELMOS-PI-28-T10` | `elmos-architecture-drift` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P2 |
| `ELMOS-PI-29-T01` | `elmos-risk-technical-debt` | 计算复杂度、重复、循环、扇入扇出、变更频率和 ownership | implementation | P2 |
| `ELMOS-PI-29-T02` | `elmos-risk-technical-debt` | 融合测试覆盖、故障、延迟、漏洞、过期依赖和业务关键度 | implementation | P2 |
| `ELMOS-PI-29-T03` | `elmos-risk-technical-debt` | 生成文件/模块/服务级风险评分并解释因子 | implementation | P2 |
| `ELMOS-PI-29-T04` | `elmos-risk-technical-debt` | 识别 God module、shotgun surgery、orphan code、unstable dependency | implementation | P2 |
| `ELMOS-PI-29-T05` | `elmos-risk-technical-debt` | 形成修复候选、成本区间和依赖顺序 | implementation | P2 |
| `ELMOS-PI-29-T06` | `elmos-risk-technical-debt` | 生成热力图和趋势 | implementation | P2 |
| `ELMOS-PI-29-T07` | `elmos-risk-technical-debt` | 实现权限、安全和不可信输入防护 | security | P2 |
| `ELMOS-PI-29-T08` | `elmos-risk-technical-debt` | 接入日志、指标、Trace、错误分类和审计 | observability | P2 |
| `ELMOS-PI-29-T09` | `elmos-risk-technical-debt` | 建立单元、契约、集成、E2E 与回归测试 | testing | P2 |
| `ELMOS-PI-29-T10` | `elmos-risk-technical-debt` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P2 |
| `ELMOS-PI-30-T01` | `elmos-security-threat-model` | 识别资产、Actor、入口、信任边界和数据分类 | implementation | P2 |
| `ELMOS-PI-30-T02` | `elmos-security-threat-model` | 执行 SAST/SCA/secret/IaC/API auth 检查 | implementation | P2 |
| `ELMOS-PI-30-T03` | `elmos-security-threat-model` | 基于 STRIDE/项目规则生成威胁候选 | implementation | P2 |
| `ELMOS-PI-30-T04` | `elmos-security-threat-model` | 构建攻击路径并结合可达性和运行证据排序 | implementation | P2 |
| `ELMOS-PI-30-T05` | `elmos-security-threat-model` | 关联漏洞到功能、代码、数据、部署和测试 | implementation | P2 |
| `ELMOS-PI-30-T06` | `elmos-security-threat-model` | 生成修复、验证和残余风险记录 | implementation | P2 |
| `ELMOS-PI-30-T07` | `elmos-security-threat-model` | 实现权限、安全和不可信输入防护 | security | P2 |
| `ELMOS-PI-30-T08` | `elmos-security-threat-model` | 接入日志、指标、Trace、错误分类和审计 | observability | P2 |
| `ELMOS-PI-30-T09` | `elmos-security-threat-model` | 建立单元、契约、集成、E2E 与回归测试 | testing | P2 |
| `ELMOS-PI-30-T10` | `elmos-security-threat-model` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P2 |

## 预期交付物

- `qa-api.yaml`（由 `elmos-project-search-qa` 负责）
- `qa-evaluation-dataset.jsonl`（由 `elmos-project-search-qa` 负责）
- `qa-eval-report.md`（由 `elmos-project-search-qa` 负责）
- `impact-report.json`（由 `elmos-impact-analysis` 负责）
- `regression-plan.yaml`（由 `elmos-impact-analysis` 负责）
- `architecture-rules.yaml`（由 `elmos-architecture-rules` 负责）
- `rule-engine-report.json`（由 `elmos-architecture-rules` 负责）
- `drift-report.json`（由 `elmos-architecture-drift` 负责）
- `architecture-diff.svg`（由 `elmos-architecture-drift` 负责）
- `risk-register.yaml`（由 `elmos-risk-technical-debt` 负责）
- `technical-debt-backlog.yaml`（由 `elmos-risk-technical-debt` 负责）
- `risk-heatmap.json`（由 `elmos-risk-technical-debt` 负责）
- `threat-model.md`（由 `elmos-security-threat-model` 负责）
- `security-findings.sarif`（由 `elmos-security-threat-model` 负责）
- `attack-paths.json`（由 `elmos-security-threat-model` 负责）
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
| `AC-25-01` | `elmos-project-search-qa` | 黄金问题集准确率、引用正确率和无回答准确率达到目标。 | required |
| `AC-25-02` | `elmos-project-search-qa` | 跨多跳路径问题可返回完整路径。 | required |
| `AC-25-03` | `elmos-project-search-qa` | 权限与 prompt injection 红队通过。 | required |
| `AC-25-04` | `elmos-project-search-qa` | 过期索引有清晰提示。 | preferred |
| `AC-25-05` | `elmos-project-search-qa` | 用户纠错可进入评测而非直接改写事实。 | preferred |
| `AC-26-01` | `elmos-impact-analysis` | 基准变更集召回率优先达到目标。 | required |
| `AC-26-02` | `elmos-impact-analysis` | 每个受影响项可解释路径。 | required |
| `AC-26-03` | `elmos-impact-analysis` | 最小测试集覆盖已知失败回归。 | required |
| `AC-26-04` | `elmos-impact-analysis` | 受影响 artifact 被正确标 stale/regen。 | preferred |
| `AC-26-05` | `elmos-impact-analysis` | 大图分析在预算内完成或可恢复。 | preferred |
| `AC-27-01` | `elmos-architecture-rules` | 规则 DSL 有 Schema 和单元测试。 | required |
| `AC-27-02` | `elmos-architecture-rules` | 已知违规被稳定检测。 | required |
| `AC-27-03` | `elmos-architecture-rules` | 例外到期后恢复失败。 | required |
| `AC-27-04` | `elmos-architecture-rules` | CI 输出可定位到代码和路径。 | preferred |
| `AC-27-05` | `elmos-architecture-rules` | 增量结果与全量结果一致。 | preferred |
| `AC-28-01` | `elmos-architecture-drift` | 基准漂移场景全部正确分类。 | required |
| `AC-28-02` | `elmos-architecture-drift` | 误报可通过规则/override 解释性降低。 | required |
| `AC-28-03` | `elmos-architecture-drift` | 接受变更生成可审计基线版本。 | required |
| `AC-28-04` | `elmos-architecture-drift` | 文档和图表 stale 状态联动。 | preferred |
| `AC-28-05` | `elmos-architecture-drift` | PR 中新增违规边能阻断。 | preferred |
| `AC-29-01` | `elmos-risk-technical-debt` | 风险排序在历史缺陷回放中有可测预测力。 | required |
| `AC-29-02` | `elmos-risk-technical-debt` | 每项技术债有证据、owner、影响和完成条件。 | required |
| `AC-29-03` | `elmos-risk-technical-debt` | 热力图可下钻。 | required |
| `AC-29-04` | `elmos-risk-technical-debt` | 数据缺失明确展示。 | preferred |
| `AC-29-05` | `elmos-risk-technical-debt` | 优先级变化可解释。 | preferred |
| `AC-30-01` | `elmos-security-threat-model` | 关键入口有认证/授权检查覆盖。 | required |
| `AC-30-02` | `elmos-security-threat-model` | 已知测试漏洞可检测。 | required |
| `AC-30-03` | `elmos-security-threat-model` | 威胁模型包含资产、边界、威胁、控制和残余风险。 | required |
| `AC-30-04` | `elmos-security-threat-model` | 修复后可重跑并闭环证据。 | preferred |
| `AC-30-05` | `elmos-security-threat-model` | 高危未处置时不能通过生产认证。 | preferred |

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

- [ ] 本批次 60 条任务均已分类为 done/waived，并附责任人与证据。
- [ ] 本批次 30 个验收场景全部通过，或存在有期限、可审计的 waiver。
- [ ] 仓库级测试与 `python3 scripts/validate_skillpack.py` 通过。
- [ ] `EXECUTION_REPORT.md` 明确已完成、未完成、已知限制、系统运行时间、人工审核量和下一批入口。
