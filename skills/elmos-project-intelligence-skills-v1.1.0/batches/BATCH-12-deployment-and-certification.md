# BATCH-12-deployment-and-certification — 生产部署与 E1–E5 认证

## 目标

完成 SaaS、私有化、离线部署及分级生产认证。

本批次必须交付可运行垂直切片，不接受只完成接口、空页面、TODO、伪数据或未执行测试。

## 前置条件

- `BATCH-00-product-and-reference-architecture` 已达到退出门禁。
- `BATCH-07-search-impact-governance-analysis` 已达到退出门禁。
- `BATCH-10-scale-and-observability` 已达到退出门禁。
- `BATCH-11-testing-conversion-estimation` 已达到退出门禁。
- 已冻结目标分支/Commit，并记录工作区脏状态。
- 已建立本批次 checkpoint、回滚点、权限范围和系统 wall-clock ETA P50/P90。

## Skill 执行顺序

| 顺序 | Skill | 目标 | 直接依赖 |
|---:|---|---|---|
| 1 | `elmos-deployment-private-cloud` | 提供可升级、可回滚、可观测、可备份并满足代码数据驻留要求的生产部署。 | `elmos-reference-architecture`, `elmos-security-threat-model`, `elmos-observability-slo` |
| 2 | `elmos-release-certification` | 用证据驱动的门禁决定是否可试用、可团队使用、可生产或可关键业务部署。 | `elmos-testing-evaluation`, `elmos-security-threat-model`, `elmos-deployment-private-cloud` |

## 实施任务

| Task | Skill | 标题 | 类型 | 优先级 |
|---|---|---|---|---|
| `ELMOS-PI-41-T01` | `elmos-deployment-private-cloud` | 定义服务镜像、依赖、资源和安全上下文 | implementation | P3 |
| `ELMOS-PI-41-T02` | `elmos-deployment-private-cloud` | 提供本地 Compose 与生产 Kubernetes/Helm | implementation | P3 |
| `ELMOS-PI-41-T03` | `elmos-deployment-private-cloud` | 配置数据库、图存储、对象存储、Temporal、缓存和可观测性 | implementation | P3 |
| `ELMOS-PI-41-T04` | `elmos-deployment-private-cloud` | 实现 egress allowlist、Secrets、TLS、SSO 和数据驻留 | implementation | P3 |
| `ELMOS-PI-41-T05` | `elmos-deployment-private-cloud` | 制定备份、恢复、升级、Schema migration 和回滚 | implementation | P3 |
| `ELMOS-PI-41-T06` | `elmos-deployment-private-cloud` | 执行灾难恢复、节点故障和版本升级演练 | implementation | P3 |
| `ELMOS-PI-41-T07` | `elmos-deployment-private-cloud` | 实现权限、安全和不可信输入防护 | security | P3 |
| `ELMOS-PI-41-T08` | `elmos-deployment-private-cloud` | 接入日志、指标、Trace、错误分类和审计 | observability | P3 |
| `ELMOS-PI-41-T09` | `elmos-deployment-private-cloud` | 建立单元、契约、集成、E2E 与回归测试 | testing | P3 |
| `ELMOS-PI-41-T10` | `elmos-deployment-private-cloud` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P3 |
| `ELMOS-PI-42-T01` | `elmos-release-certification` | 定义 E1 原型、E2 可验证、E3 团队级、E4 生产级、E5 关键业务级标准 | implementation | P3 |
| `ELMOS-PI-42-T02` | `elmos-release-certification` | 收集构建、测试、评测、性能、安全、权限、恢复和文档证据 | implementation | P3 |
| `ELMOS-PI-42-T03` | `elmos-release-certification` | 验证证据新鲜度、revision、环境和完整性 | implementation | P3 |
| `ELMOS-PI-42-T04` | `elmos-release-certification` | 执行硬门禁与可审批 waiver | implementation | P3 |
| `ELMOS-PI-42-T05` | `elmos-release-certification` | 生成失败项、修复任务、残余风险和重新认证范围 | implementation | P3 |
| `ELMOS-PI-42-T06` | `elmos-release-certification` | 冻结并签名认证报告 | implementation | P3 |
| `ELMOS-PI-42-T07` | `elmos-release-certification` | 实现权限、安全和不可信输入防护 | security | P3 |
| `ELMOS-PI-42-T08` | `elmos-release-certification` | 接入日志、指标、Trace、错误分类和审计 | observability | P3 |
| `ELMOS-PI-42-T09` | `elmos-release-certification` | 建立单元、契约、集成、E2E 与回归测试 | testing | P3 |
| `ELMOS-PI-42-T10` | `elmos-release-certification` | 更新 API、Schema、文档、追踪矩阵并完成验收 | documentation | P3 |

## 预期交付物

- `deploy/`（由 `elmos-deployment-private-cloud` 负责）
- `private-deployment-guide.md`（由 `elmos-deployment-private-cloud` 负责）
- `dr-test-report.md`（由 `elmos-deployment-private-cloud` 负责）
- `certification-matrix.yaml`（由 `elmos-release-certification` 负责）
- `certification-report.md`（由 `elmos-release-certification` 负责）
- `signed-evidence-bundle.zip`（由 `elmos-release-certification` 负责）
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
| `AC-41-01` | `elmos-deployment-private-cloud` | 从空环境可按文档部署。 | required |
| `AC-41-02` | `elmos-deployment-private-cloud` | 备份恢复演练通过。 | required |
| `AC-41-03` | `elmos-deployment-private-cloud` | 滚动升级和回滚无数据破坏。 | required |
| `AC-41-04` | `elmos-deployment-private-cloud` | 安全扫描达到门禁。 | preferred |
| `AC-41-05` | `elmos-deployment-private-cloud` | 私有化环境可在无公网模式运行核心能力。 | preferred |
| `AC-42-01` | `elmos-release-certification` | 所有门禁有明确证据。 | required |
| `AC-42-02` | `elmos-release-certification` | 失败可生成可执行修复 backlog。 | required |
| `AC-42-03` | `elmos-release-certification` | 签名包可离线验证。 | required |
| `AC-42-04` | `elmos-release-certification` | 认证状态变更有职责分离与审计。 | preferred |
| `AC-42-05` | `elmos-release-certification` | E4/E5 通过灾备和安全红队。 | preferred |

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
