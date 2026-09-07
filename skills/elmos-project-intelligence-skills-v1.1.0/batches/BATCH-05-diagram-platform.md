# BATCH-05-diagram-platform — Artifact 版本底座与图表平台

## 目标

建立稳定 Artifact 生命周期、统一 Diagram Spec、渲染和在线编辑。

本批次必须交付可运行垂直切片，不接受只完成接口、空页面、TODO、伪数据或未执行测试。

## 前置条件

- `BATCH-02-graphs-and-evidence` 已达到退出门禁。
- 已冻结目标分支/Commit，并记录工作区脏状态。
- 已建立本批次 checkpoint、回滚点、权限范围和系统 wall-clock ETA P50/P90。

## Skill 执行顺序

| 顺序 | Skill | 目标 | 直接依赖 |
|---:|---|---|---|
| 1 | `elmos-diagram-spec-engine` | 以可版本化的中立 DSL 表达节点、边、分组、证据、布局约束和交互，避免图表只剩不可维护图片。 | `elmos-project-intelligence-graph` |
| 2 | `elmos-diagram-rendering` | 提供一致、清晰、可缩放、可缓存且可回源的自动图表输出。 | `elmos-diagram-spec-engine` |
| 3 | `elmos-artifact-versioning-human-lock` | 确保自动更新不会破坏人工维护内容，同时保持与代码 revision 的一致性。 | `elmos-evidence-provenance` |
| 4 | `elmos-diagram-editor` | 让用户编辑语义而非破坏性修改图片，并在重新生成时安全合并自动变化。 | `elmos-diagram-rendering`, `elmos-artifact-versioning-human-lock` |

## 实施任务

| Task | Skill | 标题 | 类型 | 优先级 |
|---|---|---|---|---|
| `ELMOS-PI-19-T01` | `elmos-diagram-spec-engine` | 定义 diagram metadata、nodes、edges、groups、ports、views 和 evidence refs | implementation | P1 |
| `ELMOS-PI-19-T02` | `elmos-diagram-spec-engine` | 为 C4、BPMN、Sequence、State、ER、DFD、Mindmap、Deployment 等定义 profile | implementation | P1 |
| `ELMOS-PI-19-T03` | `elmos-diagram-spec-engine` | 定义折叠、聚合、分页、布局 hint 和视觉语义 | implementation | P1 |
| `ELMOS-PI-19-T04` | `elmos-diagram-spec-engine` | 定义人工锁定、注释和版本 diff | implementation | P1 |
| `ELMOS-PI-19-T05` | `elmos-diagram-spec-engine` | 实现 JSON Schema 和语义校验器 | implementation | P1 |
| `ELMOS-PI-19-T06` | `elmos-diagram-spec-engine` | 提供从 Intelligence Graph 到 Diagram Spec 的投影器 | implementation | P1 |
| `ELMOS-PI-19-T07` | `elmos-diagram-spec-engine` | 实现权限、安全和不可信输入防护 | security | P1 |
| `ELMOS-PI-19-T08` | `elmos-diagram-spec-engine` | 接入日志、指标、Trace、错误分类和审计 | observability | P1 |
| `ELMOS-PI-19-T09` | `elmos-diagram-spec-engine` | 建立单元、契约、集成、E2E 与回归测试 | testing | P1 |
| `ELMOS-PI-19-T10` | `elmos-diagram-spec-engine` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P1 |
| `ELMOS-PI-20-T01` | `elmos-diagram-rendering` | 选择适合图类型的渲染器并生成中间 DSL | implementation | P1 |
| `ELMOS-PI-20-T02` | `elmos-diagram-rendering` | 使用 ELK/Dagre/Graphviz 等执行自动布局 | implementation | P1 |
| `ELMOS-PI-20-T03` | `elmos-diagram-rendering` | 对大图进行聚合、分层、分页和 overview+detail | implementation | P1 |
| `ELMOS-PI-20-T04` | `elmos-diagram-rendering` | 嵌入 element ID、evidence link 和 accessibility metadata | implementation | P1 |
| `ELMOS-PI-20-T05` | `elmos-diagram-rendering` | 沙箱化渲染进程并限制 CPU/内存/时间 | implementation | P1 |
| `ELMOS-PI-20-T06` | `elmos-diagram-rendering` | 缓存 spec hash + renderer version + theme 的结果 | implementation | P1 |
| `ELMOS-PI-20-T07` | `elmos-diagram-rendering` | 实现权限、安全和不可信输入防护 | security | P1 |
| `ELMOS-PI-20-T08` | `elmos-diagram-rendering` | 接入日志、指标、Trace、错误分类和审计 | observability | P1 |
| `ELMOS-PI-20-T09` | `elmos-diagram-rendering` | 建立单元、契约、集成、E2E 与回归测试 | testing | P1 |
| `ELMOS-PI-20-T10` | `elmos-diagram-rendering` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P1 |
| `ELMOS-PI-21-T01` | `elmos-diagram-editor` | 实现缩放、平移、搜索、折叠、下钻和 mini-map | implementation | P1 |
| `ELMOS-PI-21-T02` | `elmos-diagram-editor` | 支持节点重命名、说明、分组、移动、隐藏和手工连线 | implementation | P1 |
| `ELMOS-PI-21-T03` | `elmos-diagram-editor` | 区分事实字段、展示字段和建议字段的编辑权限 | implementation | P1 |
| `ELMOS-PI-21-T04` | `elmos-diagram-editor` | 保存人工 override 和锁定范围 | implementation | P1 |
| `ELMOS-PI-21-T05` | `elmos-diagram-editor` | 对新自动 Spec 进行三方合并并显示冲突 | implementation | P1 |
| `ELMOS-PI-21-T06` | `elmos-diagram-editor` | 支持评论、审批、撤销/重做和版本回退 | implementation | P1 |
| `ELMOS-PI-21-T07` | `elmos-diagram-editor` | 实现权限、安全和不可信输入防护 | security | P1 |
| `ELMOS-PI-21-T08` | `elmos-diagram-editor` | 接入日志、指标、Trace、错误分类和审计 | observability | P1 |
| `ELMOS-PI-21-T09` | `elmos-diagram-editor` | 建立单元、契约、集成、E2E 与回归测试 | testing | P1 |
| `ELMOS-PI-21-T10` | `elmos-diagram-editor` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P1 |
| `ELMOS-PI-32-T01` | `elmos-artifact-versioning-human-lock` | 定义 Artifact、Block、Element、Version、Lock、Override 和 Review 模型 | implementation | P1 |
| `ELMOS-PI-32-T02` | `elmos-artifact-versioning-human-lock` | 为段落、图节点、PPT 页面和表格分配稳定 ID | implementation | P1 |
| `ELMOS-PI-32-T03` | `elmos-artifact-versioning-human-lock` | 保存 base-generated、human-patch 和 next-generated 三方数据 | implementation | P1 |
| `ELMOS-PI-32-T04` | `elmos-artifact-versioning-human-lock` | 执行语义合并并分类自动可合并/冲突/失效 | implementation | P1 |
| `ELMOS-PI-32-T05` | `elmos-artifact-versioning-human-lock` | 支持 Draft、Reviewed、Approved、Certified 生命周期 | implementation | P1 |
| `ELMOS-PI-32-T06` | `elmos-artifact-versioning-human-lock` | 提供回滚、比较、审计和保留策略 | implementation | P1 |
| `ELMOS-PI-32-T07` | `elmos-artifact-versioning-human-lock` | 实现权限、安全和不可信输入防护 | security | P1 |
| `ELMOS-PI-32-T08` | `elmos-artifact-versioning-human-lock` | 接入日志、指标、Trace、错误分类和审计 | observability | P1 |
| `ELMOS-PI-32-T09` | `elmos-artifact-versioning-human-lock` | 建立单元、契约、集成、E2E 与回归测试 | testing | P1 |
| `ELMOS-PI-32-T10` | `elmos-artifact-versioning-human-lock` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P1 |

## 预期交付物

- `schemas/diagram-spec.schema.json`（由 `elmos-diagram-spec-engine` 负责）
- `diagram-profiles/`（由 `elmos-diagram-spec-engine` 负责）
- `services/diagram-renderer`（由 `elmos-diagram-rendering` 负责）
- `render-compatibility-matrix.md`（由 `elmos-diagram-rendering` 负责）
- `artifact-schema.json`（由 `elmos-artifact-versioning-human-lock` 负责）
- `merge-policy.md`（由 `elmos-artifact-versioning-human-lock` 负责）
- `artifact-lifecycle-tests.md`（由 `elmos-artifact-versioning-human-lock` 负责）
- `apps/insight-web/src/modules/diagram-editor`（由 `elmos-diagram-editor` 负责）
- `diagram-merge-tests.md`（由 `elmos-diagram-editor` 负责）
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
| `AC-19-01` | `elmos-diagram-spec-engine` | 所有目录中的核心图表类型通过 Schema。 | required |
| `AC-19-02` | `elmos-diagram-spec-engine` | 相同图谱与参数生成稳定 element ID。 | required |
| `AC-19-03` | `elmos-diagram-spec-engine` | 无效边和孤立证据引用被拒绝。 | required |
| `AC-19-04` | `elmos-diagram-spec-engine` | Spec 可由至少两个渲染器消费。 | preferred |
| `AC-19-05` | `elmos-diagram-spec-engine` | 版本迁移保持语义等价。 | preferred |
| `AC-20-01` | `elmos-diagram-rendering` | 核心图表快照测试通过。 | required |
| `AC-20-02` | `elmos-diagram-rendering` | 1000 节点压力图有受控降级且不 OOM。 | required |
| `AC-20-03` | `elmos-diagram-rendering` | SVG 中 element ID 与 Spec 一致。 | required |
| `AC-20-04` | `elmos-diagram-rendering` | 同版本确定性渲染达到目标。 | preferred |
| `AC-20-05` | `elmos-diagram-rendering` | 恶意 DSL 安全测试通过。 | preferred |
| `AC-21-01` | `elmos-diagram-editor` | 自动再生成后布局和锁定内容正确保留。 | required |
| `AC-21-02` | `elmos-diagram-editor` | 冲突可逐项解决并审计。 | required |
| `AC-21-03` | `elmos-diagram-editor` | 撤销/重做覆盖核心操作。 | required |
| `AC-21-04` | `elmos-diagram-editor` | 图节点点击可回代码和证据。 | preferred |
| `AC-21-05` | `elmos-diagram-editor` | 导出再导入不丢人工 override。 | preferred |
| `AC-32-01` | `elmos-artifact-versioning-human-lock` | 三方合并核心场景通过。 | required |
| `AC-32-02` | `elmos-artifact-versioning-human-lock` | 锁定内容跨再生成保持。 | required |
| `AC-32-03` | `elmos-artifact-versioning-human-lock` | 每个版本可完整重建或验证。 | required |
| `AC-32-04` | `elmos-artifact-versioning-human-lock` | 审批和状态转换权限正确。 | preferred |
| `AC-32-05` | `elmos-artifact-versioning-human-lock` | stale artifact 不可误标 Certified。 | preferred |

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
