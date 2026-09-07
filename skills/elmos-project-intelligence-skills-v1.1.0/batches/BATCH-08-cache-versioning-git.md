# BATCH-08-cache-versioning-git — 增量缓存、失效传播与 Git PR

## 目标

使大型长任务增量、可恢复，并把 artifact 变化安全交付到 Git。

本批次必须交付可运行垂直切片，不接受只完成接口、空页面、TODO、伪数据或未执行测试。

## 前置条件

- `BATCH-00-product-and-reference-architecture` 已达到退出门禁。
- `BATCH-02-graphs-and-evidence` 已达到退出门禁。
- `BATCH-05-diagram-platform` 已达到退出门禁。
- `BATCH-07-search-impact-governance-analysis` 已达到退出门禁。
- 已冻结目标分支/Commit，并记录工作区脏状态。
- 已建立本批次 checkpoint、回滚点、权限范围和系统 wall-clock ETA P50/P90。

## Skill 执行顺序

| 顺序 | Skill | 目标 | 直接依赖 |
|---:|---|---|---|
| 1 | `elmos-incremental-analysis-cache` | 让解析、图谱、解释、图表、文档和 PPT 能按最小影响范围重算，并在中断后继续。 | `elmos-reference-architecture`, `elmos-evidence-provenance` |
| 2 | `elmos-git-pr-automation` | 用最小权限和幂等工作流将 Elmos 输出纳入正常代码审查。 | `elmos-artifact-versioning-human-lock`, `elmos-impact-analysis` |

## 实施任务

| Task | Skill | 标题 | 类型 | 优先级 |
|---|---|---|---|---|
| `ELMOS-PI-31-T01` | `elmos-incremental-analysis-cache` | 为 ingest、parse、graph、flow、artifact、model call 定义确定性 cache key | implementation | P2 |
| `ELMOS-PI-31-T02` | `elmos-incremental-analysis-cache` | 建立文件→symbol→graph view→claim→artifact block 的依赖索引 | implementation | P2 |
| `ELMOS-PI-31-T03` | `elmos-incremental-analysis-cache` | 根据 Git diff、配置、规则、模型和模板变化计算失效范围 | implementation | P2 |
| `ELMOS-PI-31-T04` | `elmos-incremental-analysis-cache` | 每个长阶段写原子检查点和已完成副作用 | implementation | P2 |
| `ELMOS-PI-31-T05` | `elmos-incremental-analysis-cache` | 实现暂停、恢复、重试、取消和租约接管 | implementation | P2 |
| `ELMOS-PI-31-T06` | `elmos-incremental-analysis-cache` | 记录命中率、节省 wall-clock、Token 和存储成本 | implementation | P2 |
| `ELMOS-PI-31-T07` | `elmos-incremental-analysis-cache` | 实现权限、安全和不可信输入防护 | security | P2 |
| `ELMOS-PI-31-T08` | `elmos-incremental-analysis-cache` | 接入日志、指标、Trace、错误分类和审计 | observability | P2 |
| `ELMOS-PI-31-T09` | `elmos-incremental-analysis-cache` | 建立单元、契约、集成、E2E 与回归测试 | testing | P2 |
| `ELMOS-PI-31-T10` | `elmos-incremental-analysis-cache` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P2 |
| `ELMOS-PI-33-T01` | `elmos-git-pr-automation` | 确认目标仓库、base revision、写权限和分支策略 | implementation | P2 |
| `ELMOS-PI-33-T02` | `elmos-git-pr-automation` | 创建唯一工作树/分支并应用最小变更 | implementation | P2 |
| `ELMOS-PI-33-T03` | `elmos-git-pr-automation` | 运行格式、链接、Schema、测试和敏感信息检查 | implementation | P2 |
| `ELMOS-PI-33-T04` | `elmos-git-pr-automation` | 生成结构化 commit 与 PR 描述，附影响和证据 | implementation | P2 |
| `ELMOS-PI-33-T05` | `elmos-git-pr-automation` | 设置 reviewer、labels 和 required checks | implementation | P2 |
| `ELMOS-PI-33-T06` | `elmos-git-pr-automation` | 处理重复调用、base 更新、冲突和关闭回滚 | implementation | P2 |
| `ELMOS-PI-33-T07` | `elmos-git-pr-automation` | 实现权限、安全和不可信输入防护 | security | P2 |
| `ELMOS-PI-33-T08` | `elmos-git-pr-automation` | 接入日志、指标、Trace、错误分类和审计 | observability | P2 |
| `ELMOS-PI-33-T09` | `elmos-git-pr-automation` | 建立单元、契约、集成、E2E 与回归测试 | testing | P2 |
| `ELMOS-PI-33-T10` | `elmos-git-pr-automation` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P2 |

## 预期交付物

- `cache-key-spec.md`（由 `elmos-incremental-analysis-cache` 负责）
- `checkpoint-schema.json`（由 `elmos-incremental-analysis-cache` 负责）
- `cache-benchmark.md`（由 `elmos-incremental-analysis-cache` 负责）
- `git-delivery-policy.md`（由 `elmos-git-pr-automation` 负责）
- `pr-template.md`（由 `elmos-git-pr-automation` 负责）
- `git-integration-tests.md`（由 `elmos-git-pr-automation` 负责）
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
| `AC-31-01` | `elmos-incremental-analysis-cache` | 相同输入重跑命中且输出哈希一致。 | required |
| `AC-31-02` | `elmos-incremental-analysis-cache` | 修改单文件只失效预期下游。 | required |
| `AC-31-03` | `elmos-incremental-analysis-cache` | worker 强制终止后可恢复。 | required |
| `AC-31-04` | `elmos-incremental-analysis-cache` | 重复恢复不重复外部副作用。 | preferred |
| `AC-31-05` | `elmos-incremental-analysis-cache` | 缓存指标可按项目/阶段查看。 | preferred |
| `AC-33-01` | `elmos-git-pr-automation` | 重复请求只产生一个有效 PR。 | required |
| `AC-33-02` | `elmos-git-pr-automation` | base 变化能重新基线或明确冲突。 | required |
| `AC-33-03` | `elmos-git-pr-automation` | PR 检查失败会阻止完成状态。 | required |
| `AC-33-04` | `elmos-git-pr-automation` | 审计可追踪到发起用户和生成版本。 | preferred |
| `AC-33-05` | `elmos-git-pr-automation` | 关闭/取消后资源被正确清理。 | preferred |

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
