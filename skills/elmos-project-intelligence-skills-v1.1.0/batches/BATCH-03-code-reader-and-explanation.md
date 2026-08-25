# BATCH-03-code-reader-and-explanation — 在线代码阅读、语义导航与讲解

## 目标

交付证据化代码阅读器、跨层导航、AI 讲解和新人学习路径。

本批次必须交付可运行垂直切片，不接受只完成接口、空页面、TODO、伪数据或未执行测试。

## 前置条件

- `BATCH-01-ingestion-and-parsing` 已达到退出门禁。
- `BATCH-02-graphs-and-evidence` 已达到退出门禁。
- 已冻结目标分支/Commit，并记录工作区脏状态。
- 已建立本批次 checkpoint、回滚点、权限范围和系统 wall-clock ETA P50/P90。

## Skill 执行顺序

| 顺序 | Skill | 目标 | 直接依赖 |
|---:|---|---|---|
| 1 | `elmos-online-code-reader` | 提供快速、安全、可扩展的项目代码阅读入口，并与架构、流程、数据和转换结果双向联动。 | `elmos-repository-ingestion`, `elmos-symbol-code-graph` |
| 2 | `elmos-semantic-navigation` | 让用户从任意代码或业务节点快速追踪到上下游实现，并显示证据与不确定性。 | `elmos-online-code-reader`, `elmos-project-intelligence-graph` |
| 3 | `elmos-code-explanation` | 提供不幻觉、可切换深度、可点击证据的 AI 代码讲解。 | `elmos-semantic-navigation`, `elmos-evidence-provenance` |
| 4 | `elmos-onboarding-learning-path` | 把庞大代码库转换为角色化、可进度跟踪、可回源的学习路径。 | `elmos-code-explanation`, `elmos-project-intelligence-graph` |

## 实施任务

| Task | Skill | 标题 | 类型 | 优先级 |
|---|---|---|---|---|
| `ELMOS-PI-09-T01` | `elmos-online-code-reader` | 建立项目/仓库/分支/Commit 选择器和虚拟化文件树 | implementation | P0 |
| `ELMOS-PI-09-T02` | `elmos-online-code-reader` | 接入 Monaco，支持高亮、折叠、大纲、面包屑、多标签和分屏 | implementation | P0 |
| `ELMOS-PI-09-T03` | `elmos-online-code-reader` | 实现原始/目标、Commit/Commit、自动/人工修改 Diff | implementation | P0 |
| `ELMOS-PI-09-T04` | `elmos-online-code-reader` | 实现深链：文件、行、Symbol、Claim、Diagram Node | implementation | P0 |
| `ELMOS-PI-09-T05` | `elmos-online-code-reader` | 加入书签、私人笔记、团队评论、最近阅读和收藏 | implementation | P0 |
| `ELMOS-PI-09-T06` | `elmos-online-code-reader` | 接入权限、脱敏、审计和大文件降级 | implementation | P0 |
| `ELMOS-PI-09-T07` | `elmos-online-code-reader` | 实现权限、安全和不可信输入防护 | security | P0 |
| `ELMOS-PI-09-T08` | `elmos-online-code-reader` | 接入日志、指标、Trace、错误分类和审计 | observability | P0 |
| `ELMOS-PI-09-T09` | `elmos-online-code-reader` | 建立单元、契约、集成、E2E 与回归测试 | testing | P0 |
| `ELMOS-PI-09-T10` | `elmos-online-code-reader` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P0 |
| `ELMOS-PI-10-T01` | `elmos-semantic-navigation` | 实现 Definition、References、Implementations、Type Hierarchy、Call Hierarchy 查询 | implementation | P0 |
| `ELMOS-PI-10-T02` | `elmos-semantic-navigation` | 实现页面→API→Service→Repository→Table 与反向路径 | implementation | P0 |
| `ELMOS-PI-10-T03` | `elmos-semantic-navigation` | 实现 Topic→Producer/Consumer、Config→Reader、Test→Target 的导航 | implementation | P0 |
| `ELMOS-PI-10-T04` | `elmos-semantic-navigation` | 为动态候选显示置信度和多个可能目标 | implementation | P0 |
| `ELMOS-PI-10-T05` | `elmos-semantic-navigation` | 支持路径限制、深度、边类型和 revision 过滤 | implementation | P0 |
| `ELMOS-PI-10-T06` | `elmos-semantic-navigation` | 记录导航性能与失败原因 | implementation | P0 |
| `ELMOS-PI-10-T07` | `elmos-semantic-navigation` | 实现权限、安全和不可信输入防护 | security | P0 |
| `ELMOS-PI-10-T08` | `elmos-semantic-navigation` | 接入日志、指标、Trace、错误分类和审计 | observability | P0 |
| `ELMOS-PI-10-T09` | `elmos-semantic-navigation` | 建立单元、契约、集成、E2E 与回归测试 | testing | P0 |
| `ELMOS-PI-10-T10` | `elmos-semantic-navigation` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P0 |
| `ELMOS-PI-11-T01` | `elmos-code-explanation` | 解析用户范围和受众：管理、产品、架构、开发、测试、运维、安全 | implementation | P1 |
| `ELMOS-PI-11-T02` | `elmos-code-explanation` | 检索最小充分上下文，不整仓库塞入模型 | implementation | P1 |
| `ELMOS-PI-11-T03` | `elmos-code-explanation` | 先生成事实清单，再生成解释、风险和建议 | implementation | P1 |
| `ELMOS-PI-11-T04` | `elmos-code-explanation` | 将每个关键 claim 绑定证据并标识可信度 | implementation | P1 |
| `ELMOS-PI-11-T05` | `elmos-code-explanation` | 输出一段式、逐步、教学、审查等模式 | implementation | P1 |
| `ELMOS-PI-11-T06` | `elmos-code-explanation` | 缓存相同 revision/scope/prompt version 结果 | implementation | P1 |
| `ELMOS-PI-11-T07` | `elmos-code-explanation` | 实现权限、安全和不可信输入防护 | security | P1 |
| `ELMOS-PI-11-T08` | `elmos-code-explanation` | 接入日志、指标、Trace、错误分类和审计 | observability | P1 |
| `ELMOS-PI-11-T09` | `elmos-code-explanation` | 建立单元、契约、集成、E2E 与回归测试 | testing | P1 |
| `ELMOS-PI-11-T10` | `elmos-code-explanation` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P1 |
| `ELMOS-PI-12-T01` | `elmos-onboarding-learning-path` | 识别项目使命、边界、核心业务能力和技术栈 | implementation | P1 |
| `ELMOS-PI-12-T02` | `elmos-onboarding-learning-path` | 为开发、测试、运维、产品、架构、安全设计不同路径 | implementation | P1 |
| `ELMOS-PI-12-T03` | `elmos-onboarding-learning-path` | 选择最具代表性的文件、调用链、流程和数据模型 | implementation | P1 |
| `ELMOS-PI-12-T04` | `elmos-onboarding-learning-path` | 生成 30 分钟、半天、3 天、2 周不同学习计划 | implementation | P1 |
| `ELMOS-PI-12-T05` | `elmos-onboarding-learning-path` | 为每阶段提供可验证任务和相关代码深链 | implementation | P1 |
| `ELMOS-PI-12-T06` | `elmos-onboarding-learning-path` | 根据用户反馈和项目变更更新路径 | implementation | P1 |
| `ELMOS-PI-12-T07` | `elmos-onboarding-learning-path` | 实现权限、安全和不可信输入防护 | security | P1 |
| `ELMOS-PI-12-T08` | `elmos-onboarding-learning-path` | 接入日志、指标、Trace、错误分类和审计 | observability | P1 |
| `ELMOS-PI-12-T09` | `elmos-onboarding-learning-path` | 建立单元、契约、集成、E2E 与回归测试 | testing | P1 |
| `ELMOS-PI-12-T10` | `elmos-onboarding-learning-path` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P1 |

## 预期交付物

- `apps/insight-web/src/modules/code-reader`（由 `elmos-online-code-reader` 负责）
- `code-reader-e2e-report.md`（由 `elmos-online-code-reader` 负责）
- `semantic-navigation-api.yaml`（由 `elmos-semantic-navigation` 负责）
- `navigation-accuracy-report.md`（由 `elmos-semantic-navigation` 负责）
- `explanation.schema.json`（由 `elmos-code-explanation` 负责）
- `explanation-eval-report.md`（由 `elmos-code-explanation` 负责）
- `onboarding-guide.md`（由 `elmos-onboarding-learning-path` 负责）
- `learning-path.json`（由 `elmos-onboarding-learning-path` 负责）
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
| `AC-09-01` | `elmos-online-code-reader` | 100k 文件项目文件树可交互且不冻结。 | required |
| `AC-09-02` | `elmos-online-code-reader` | 代码打开、标签切换和定位达到体验 SLO。 | required |
| `AC-09-03` | `elmos-online-code-reader` | 复制的深链在同权限用户下可复现。 | required |
| `AC-09-04` | `elmos-online-code-reader` | Diff 能区分自动生成、人工编辑和转换来源。 | preferred |
| `AC-09-05` | `elmos-online-code-reader` | 权限撤销后缓存内容不可继续访问。 | preferred |
| `AC-10-01` | `elmos-semantic-navigation` | 基准项目主要语言导航准确率达到目标。 | required |
| `AC-10-02` | `elmos-semantic-navigation` | 跨层路径可从页面追到数据表并返回证据。 | required |
| `AC-10-03` | `elmos-semantic-navigation` | 大扇出查询有摘要和继续加载。 | required |
| `AC-10-04` | `elmos-semantic-navigation` | 失效 symbol 链接有重定位或明确错误。 | preferred |
| `AC-10-05` | `elmos-semantic-navigation` | 导航权限测试全部通过。 | preferred |
| `AC-11-01` | `elmos-code-explanation` | 关键事实 claim 覆盖率达到目标。 | required |
| `AC-11-02` | `elmos-code-explanation` | 随机证据链接有效。 | required |
| `AC-11-03` | `elmos-code-explanation` | 同一 revision 重复生成事实部分稳定。 | required |
| `AC-11-04` | `elmos-code-explanation` | 安全测试能抵御注释/README 指令注入。 | preferred |
| `AC-11-05` | `elmos-code-explanation` | 用户可反馈错误并形成 override/评测样本。 | preferred |
| `AC-12-01` | `elmos-onboarding-learning-path` | 用户能沿路径定位并运行最小开发闭环。 | required |
| `AC-12-02` | `elmos-onboarding-learning-path` | 每个学习节点有目标、材料、练习和完成条件。 | required |
| `AC-12-03` | `elmos-onboarding-learning-path` | 路径中的文件和链接全部存在。 | required |
| `AC-12-04` | `elmos-onboarding-learning-path` | 项目变化后受影响节点被标记 stale。 | preferred |
| `AC-12-05` | `elmos-onboarding-learning-path` | 角色间内容明显差异化。 | preferred |

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

- [ ] 本批次 40 条任务均已分类为 done/waived，并附责任人与证据。
- [ ] 本批次 20 个验收场景全部通过，或存在有期限、可审计的 waiver。
- [ ] 仓库级测试与 `python3 scripts/validate_skillpack.py` 通过。
- [ ] `EXECUTION_REPORT.md` 明确已完成、未完成、已知限制、系统运行时间、人工审核量和下一批入口。
