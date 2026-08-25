# BATCH-06-documents-presentations-reports — 架构文档、项目 PPT 与交付报告

## 目标

从同一事实底座生成可编辑、可回源、可审阅的文档、PPT 和离线报告包。

本批次必须交付可运行垂直切片，不接受只完成接口、空页面、TODO、伪数据或未执行测试。

## 前置条件

- `BATCH-02-graphs-and-evidence` 已达到退出门禁。
- `BATCH-05-diagram-platform` 已达到退出门禁。
- 已冻结目标分支/Commit，并记录工作区脏状态。
- 已建立本批次 checkpoint、回滚点、权限范围和系统 wall-clock ETA P50/P90。

## Skill 执行顺序

| 顺序 | Skill | 目标 | 直接依赖 |
|---:|---|---|---|
| 1 | `elmos-architecture-documentation` | 建立多文档、可引用、可增量更新、可人工维护的项目知识体系。 | `elmos-evidence-provenance`, `elmos-diagram-rendering` |
| 2 | `elmos-presentation-generation` | 把统一项目事实、图表和指标转为针对受众的可编辑演示文稿，并保留证据和演讲备注。 | `elmos-architecture-documentation`, `elmos-diagram-rendering` |
| 3 | `elmos-project-report-bundle` | 提供一次可下载、可审计、可复现的项目全景交付，而不是零散文件。 | `elmos-architecture-documentation`, `elmos-presentation-generation`, `elmos-evidence-provenance` |

## 实施任务

| Task | Skill | 标题 | 类型 | 优先级 |
|---|---|---|---|---|
| `ELMOS-PI-22-T01` | `elmos-architecture-documentation` | 选择文档类型、受众、深度和模板 | implementation | P1 |
| `ELMOS-PI-22-T02` | `elmos-architecture-documentation` | 生成事实大纲并验证覆盖与证据 | implementation | P1 |
| `ELMOS-PI-22-T03` | `elmos-architecture-documentation` | 生成正文、图表引用、表格、风险和未知项 | implementation | P1 |
| `ELMOS-PI-22-T04` | `elmos-architecture-documentation` | 为关键 claim 建立证据链接 | implementation | P1 |
| `ELMOS-PI-22-T05` | `elmos-architecture-documentation` | 与已有文档执行段落级三方合并 | implementation | P1 |
| `ELMOS-PI-22-T06` | `elmos-architecture-documentation` | 导出格式并生成可访问性、链接和一致性检查 | implementation | P1 |
| `ELMOS-PI-22-T07` | `elmos-architecture-documentation` | 实现权限、安全和不可信输入防护 | security | P1 |
| `ELMOS-PI-22-T08` | `elmos-architecture-documentation` | 接入日志、指标、Trace、错误分类和审计 | observability | P1 |
| `ELMOS-PI-22-T09` | `elmos-architecture-documentation` | 建立单元、契约、集成、E2E 与回归测试 | testing | P1 |
| `ELMOS-PI-22-T10` | `elmos-architecture-documentation` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P1 |
| `ELMOS-PI-23-T01` | `elmos-presentation-generation` | 选择演示类型并建立答案优先的故事线 | implementation | P1 |
| `ELMOS-PI-23-T02` | `elmos-presentation-generation` | 为每页定义目的、主结论、证据、图表和备注 | implementation | P1 |
| `ELMOS-PI-23-T03` | `elmos-presentation-generation` | 生成或复用架构图、流程图和指标图 | implementation | P1 |
| `ELMOS-PI-23-T04` | `elmos-presentation-generation` | 使用模板引擎创建可编辑文本、形状、表格和图表 | implementation | P1 |
| `ELMOS-PI-23-T05` | `elmos-presentation-generation` | 检查溢出、可读性、引用、品牌和敏感信息 | implementation | P1 |
| `ELMOS-PI-23-T06` | `elmos-presentation-generation` | 按 slide stable ID 支持增量更新和人工锁定 | implementation | P1 |
| `ELMOS-PI-23-T07` | `elmos-presentation-generation` | 实现权限、安全和不可信输入防护 | security | P1 |
| `ELMOS-PI-23-T08` | `elmos-presentation-generation` | 接入日志、指标、Trace、错误分类和审计 | observability | P1 |
| `ELMOS-PI-23-T09` | `elmos-presentation-generation` | 建立单元、契约、集成、E2E 与回归测试 | testing | P1 |
| `ELMOS-PI-23-T10` | `elmos-presentation-generation` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P1 |
| `ELMOS-PI-24-T01` | `elmos-project-report-bundle` | 冻结项目 revision 和所有引用 artifact version | implementation | P1 |
| `ELMOS-PI-24-T02` | `elmos-project-report-bundle` | 根据报告类型选取章节、图表、PPT 和原始证明 | implementation | P1 |
| `ELMOS-PI-24-T03` | `elmos-project-report-bundle` | 检查 claim/evidence 完整性和 stale 状态 | implementation | P1 |
| `ELMOS-PI-24-T04` | `elmos-project-report-bundle` | 应用脱敏、水印、受众权限和保留策略 | implementation | P1 |
| `ELMOS-PI-24-T05` | `elmos-project-report-bundle` | 生成目录、交叉链接、manifest、哈希和可选签名 | implementation | P1 |
| `ELMOS-PI-24-T06` | `elmos-project-report-bundle` | 执行离线打开与完整性验证 | implementation | P1 |
| `ELMOS-PI-24-T07` | `elmos-project-report-bundle` | 实现权限、安全和不可信输入防护 | security | P1 |
| `ELMOS-PI-24-T08` | `elmos-project-report-bundle` | 接入日志、指标、Trace、错误分类和审计 | observability | P1 |
| `ELMOS-PI-24-T09` | `elmos-project-report-bundle` | 建立单元、契约、集成、E2E 与回归测试 | testing | P1 |
| `ELMOS-PI-24-T10` | `elmos-project-report-bundle` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P1 |

## 预期交付物

- `docs/generated/`（由 `elmos-architecture-documentation` 负责）
- `document-manifest.json`（由 `elmos-architecture-documentation` 负责）
- `presentations/`（由 `elmos-presentation-generation` 负责）
- `slide-manifest.json`（由 `elmos-presentation-generation` 负责）
- `pptx-validation-report.md`（由 `elmos-presentation-generation` 负责）
- `delivery-bundle.zip`（由 `elmos-project-report-bundle` 负责）
- `bundle-manifest.json`（由 `elmos-project-report-bundle` 负责）
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
| `AC-22-01` | `elmos-architecture-documentation` | 文档关键 claim 证据覆盖率达到阈值。 | required |
| `AC-22-02` | `elmos-architecture-documentation` | 内部链接和代码深链有效。 | required |
| `AC-22-03` | `elmos-architecture-documentation` | 代码变更只更新受影响章节。 | required |
| `AC-22-04` | `elmos-architecture-documentation` | 人工内容在再生成后保留。 | preferred |
| `AC-22-05` | `elmos-architecture-documentation` | 导出 Markdown/DOCX/PDF 的结构一致。 | preferred |
| `AC-23-01` | `elmos-presentation-generation` | 所有文本无溢出且核心页面可编辑。 | required |
| `AC-23-02` | `elmos-presentation-generation` | 关键结论有 evidence map。 | required |
| `AC-23-03` | `elmos-presentation-generation` | 相同模板重生成能保留锁定页。 | required |
| `AC-23-04` | `elmos-presentation-generation` | 不同受众故事线显著不同。 | preferred |
| `AC-23-05` | `elmos-presentation-generation` | PPTX 可被主流 Office 软件正常打开。 | preferred |
| `AC-24-01` | `elmos-project-report-bundle` | 离线包完整可导航。 | required |
| `AC-24-02` | `elmos-project-report-bundle` | manifest 哈希验证成功。 | required |
| `AC-24-03` | `elmos-project-report-bundle` | 所有关键引用可解析。 | required |
| `AC-24-04` | `elmos-project-report-bundle` | 脱敏规则测试通过。 | preferred |
| `AC-24-05` | `elmos-project-report-bundle` | 报告状态与审批记录一致。 | preferred |

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
