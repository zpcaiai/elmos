# BATCH-01-ingestion-and-parsing — 仓库接入、指纹与多语言解析

## 目标

把代码库冻结为可复现 revision，识别技术栈并产出标准化 Code IR。

本批次必须交付可运行垂直切片，不接受只完成接口、空页面、TODO、伪数据或未执行测试。

## 前置条件

- `BATCH-00-product-and-reference-architecture` 已达到退出门禁。
- 已冻结目标分支/Commit，并记录工作区脏状态。
- 已建立本批次 checkpoint、回滚点、权限范围和系统 wall-clock ETA P50/P90。

## Skill 执行顺序

| 顺序 | Skill | 目标 | 直接依赖 |
|---:|---|---|---|
| 1 | `elmos-repository-ingestion` | 把任意受支持项目转换为不可歧义、可重放、可审计的 Project Revision。 | `elmos-reference-architecture` |
| 2 | `elmos-project-fingerprinting` | 生成可靠的技术栈与项目复杂度指纹，为后续分析选择正确工具链。 | `elmos-repository-ingestion` |
| 3 | `elmos-multilanguage-parsing` | 以可增量、可容错方式把支持语言标准化为统一符号与关系模型。 | `elmos-project-fingerprinting` |

## 实施任务

| Task | Skill | 标题 | 类型 | 优先级 |
|---|---|---|---|---|
| `ELMOS-PI-03-T01` | `elmos-repository-ingestion` | 校验来源、租户、权限和内容大小 | implementation | P0 |
| `ELMOS-PI-03-T02` | `elmos-repository-ingestion` | 解析 Git、子模块、LFS、Monorepo 和多仓库组合 | implementation | P0 |
| `ELMOS-PI-03-T03` | `elmos-repository-ingestion` | 冻结 commit SHA；上传包计算内容哈希 | implementation | P0 |
| `ELMOS-PI-03-T04` | `elmos-repository-ingestion` | 扫描文件类型、二进制、生成代码、Vendor 与敏感文件 | implementation | P0 |
| `ELMOS-PI-03-T05` | `elmos-repository-ingestion` | 写入对象存储并生成不可变 manifest | implementation | P0 |
| `ELMOS-PI-03-T06` | `elmos-repository-ingestion` | 发布 project.revision.ingested 事件 | implementation | P0 |
| `ELMOS-PI-03-T07` | `elmos-repository-ingestion` | 实现权限、安全和不可信输入防护 | security | P0 |
| `ELMOS-PI-03-T08` | `elmos-repository-ingestion` | 接入日志、指标、Trace、错误分类和审计 | observability | P0 |
| `ELMOS-PI-03-T09` | `elmos-repository-ingestion` | 建立单元、契约、集成、E2E 与回归测试 | testing | P0 |
| `ELMOS-PI-03-T10` | `elmos-repository-ingestion` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P0 |
| `ELMOS-PI-04-T01` | `elmos-project-fingerprinting` | 统计语言、文件、LOC、生成代码和测试占比 | implementation | P0 |
| `ELMOS-PI-04-T02` | `elmos-project-fingerprinting` | 识别构建系统、包管理器、框架和版本 | implementation | P0 |
| `ELMOS-PI-04-T03` | `elmos-project-fingerprinting` | 识别服务入口、UI 入口、CLI、Cron、Consumer 和 Webhook | implementation | P0 |
| `ELMOS-PI-04-T04` | `elmos-project-fingerprinting` | 识别数据库、缓存、消息、云资源和部署描述 | implementation | P0 |
| `ELMOS-PI-04-T05` | `elmos-project-fingerprinting` | 识别反射、动态加载、宏、代码生成和 FFI 风险 | implementation | P0 |
| `ELMOS-PI-04-T06` | `elmos-project-fingerprinting` | 输出解析器与运行时证据采集建议 | implementation | P0 |
| `ELMOS-PI-04-T07` | `elmos-project-fingerprinting` | 实现权限、安全和不可信输入防护 | security | P0 |
| `ELMOS-PI-04-T08` | `elmos-project-fingerprinting` | 接入日志、指标、Trace、错误分类和审计 | observability | P0 |
| `ELMOS-PI-04-T09` | `elmos-project-fingerprinting` | 建立单元、契约、集成、E2E 与回归测试 | testing | P0 |
| `ELMOS-PI-04-T10` | `elmos-project-fingerprinting` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P0 |
| `ELMOS-PI-05-T01` | `elmos-multilanguage-parsing` | 为每种语言选择 Tree-sitter、编译器前端或 LSP 适配器 | implementation | P0 |
| `ELMOS-PI-05-T02` | `elmos-multilanguage-parsing` | 解析文件并保留位置、注释、语法节点和错误节点 | implementation | P0 |
| `ELMOS-PI-05-T03` | `elmos-multilanguage-parsing` | 解析包、模块、类型、函数、变量、注解、路由和配置绑定 | implementation | P0 |
| `ELMOS-PI-05-T04` | `elmos-multilanguage-parsing` | 标准化跨语言 Symbol ID 和 Type ID | implementation | P0 |
| `ELMOS-PI-05-T05` | `elmos-multilanguage-parsing` | 关联生成代码、源映射、宏展开与 partial class | implementation | P0 |
| `ELMOS-PI-05-T06` | `elmos-multilanguage-parsing` | 按文件内容哈希增量更新 IR | implementation | P0 |
| `ELMOS-PI-05-T07` | `elmos-multilanguage-parsing` | 实现权限、安全和不可信输入防护 | security | P0 |
| `ELMOS-PI-05-T08` | `elmos-multilanguage-parsing` | 接入日志、指标、Trace、错误分类和审计 | observability | P0 |
| `ELMOS-PI-05-T09` | `elmos-multilanguage-parsing` | 建立单元、契约、集成、E2E 与回归测试 | testing | P0 |
| `ELMOS-PI-05-T10` | `elmos-multilanguage-parsing` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P0 |

## 预期交付物

- `project-manifest.json`（由 `elmos-repository-ingestion` 负责）
- `ingestion-report.json`（由 `elmos-repository-ingestion` 负责）
- `technology-fingerprint.json`（由 `elmos-project-fingerprinting` 负责）
- `analysis-plan.json`（由 `elmos-project-fingerprinting` 负责）
- `code-ir.jsonl`（由 `elmos-multilanguage-parsing` 负责）
- `parse-diagnostics.json`（由 `elmos-multilanguage-parsing` 负责）
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
| `AC-03-01` | `elmos-repository-ingestion` | 相同 revision 重复导入得到相同 manifest hash。 | required |
| `AC-03-02` | `elmos-repository-ingestion` | 断点续传不会产生重复对象。 | required |
| `AC-03-03` | `elmos-repository-ingestion` | 子模块 revision 被明确记录。 | required |
| `AC-03-04` | `elmos-repository-ingestion` | 私有凭据不出现在日志、事件或 artifact。 | preferred |
| `AC-03-05` | `elmos-repository-ingestion` | 删除项目后按保留策略可验证清除。 | preferred |
| `AC-04-01` | `elmos-project-fingerprinting` | 主语言与构建系统在基准仓库识别准确率达到目标阈值。 | required |
| `AC-04-02` | `elmos-project-fingerprinting` | 所有技术栈结论可跳转到证据文件。 | required |
| `AC-04-03` | `elmos-project-fingerprinting` | 错误识别可人工覆盖且被版本化。 | required |
| `AC-04-04` | `elmos-project-fingerprinting` | 分析计划明确列出不支持或低置信度区域。 | preferred |
| `AC-05-01` | `elmos-multilanguage-parsing` | 受支持基准仓库文件解析成功率达到设定阈值。 | required |
| `AC-05-02` | `elmos-multilanguage-parsing` | 增量修改单文件只重建受影响 shard。 | required |
| `AC-05-03` | `elmos-multilanguage-parsing` | Symbol 位置与在线代码阅读器行号一致。 | required |
| `AC-05-04` | `elmos-multilanguage-parsing` | 不支持语法有明确诊断和降级输出。 | preferred |
| `AC-05-05` | `elmos-multilanguage-parsing` | Code IR 通过 Schema 验证。 | preferred |

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
