---
name: pm-b42-shadow-canary-cutover
description: "在生产真实输入下通过影子、事件回放、双写验证、灰度、Strangler 和自动回滚安全替换旧系统. Precision Migration B42 contract; use for this exact assessment, transformation, validation, repair, evidence, or cutover scope."
---

# Batch 42：Shadow、Canary与渐进切换
## ELMOS runtime binding

- Invoke this repository Skill as `$pm-b42-shadow-canary-cutover`.
- Immutable source identity: `batch-42-shadow-canary-cutover` in `precision-migration-b01-44` (B42).
- Runtime adapter: `shadow-canary-cutover`; binding state: `DECLARED`.
- Resolve and plan with `python3 scripts/precision_migration/runtime.py plan --skill pm-b42-shadow-canary-cutover`.
- Static installation and local evidence evaluation never substitute for exact source/target execution, independent review, customer acceptance, production operation, or certification; missing evidence stays `NOT_RUN`.


## Goal

在生产真实输入下通过影子、事件回放、双写验证、灰度、Strangler 和自动回滚安全替换旧系统。

## Position in the system

- Phase: `L 证据、上线和产品化`
- Included skills: `10`
- Required status vocabulary: `PROVED | VERIFIED | CONDITIONALLY_VERIFIED | REQUIRES_ADAPTER | REQUIRES_HUMAN_REVIEW | UNSUPPORTED | FAILED`

## Batch workflow

1. 汇总证据与未解决项
2. 执行硬性发布门禁
3. 影子/Canary/渐进切换
4. 监控并自动回滚
5. 沉淀反例、规则和企业交付能力

## Shared gates

- 未解决阻断项必须为0
- 生产副作用必须可抑制、可回滚或经批准
- 证据、环境和产物必须可追踪与签名

## Dispatch rules

- 当任务涉及 **production-shadow-run** 时，调用 `../pm-b42-production-shadow-run/SKILL.md`。
- 当任务涉及 **live-event-replay** 时，调用 `../pm-b42-live-event-replay/SKILL.md`。
- 当任务涉及 **side-effect-suppression** 时，调用 `../pm-b42-side-effect-suppression/SKILL.md`。
- 当任务涉及 **dual-write-validation** 时，调用 `../pm-b42-dual-write-validation/SKILL.md`。
- 当任务涉及 **canary-traffic-planner** 时，调用 `../pm-b42-canary-traffic-planner/SKILL.md`。
- 当任务涉及 **progressive-cutover** 时，调用 `../pm-b42-progressive-cutover/SKILL.md`。
- 当任务涉及 **automatic-rollback** 时，调用 `../pm-b42-automatic-rollback/SKILL.md`。
- 当任务涉及 **migration-wave-planner** 时，调用 `../pm-b42-migration-wave-planner/SKILL.md`。
- 当任务涉及 **strangler-routing** 时，调用 `../pm-b42-strangler-routing/SKILL.md`。
- 当任务涉及 **post-cutover-monitoring** 时，调用 `../pm-b42-post-cutover-monitoring/SKILL.md`。

## Skill catalog

| Skill | Responsibility |
|---|---|
| `production-shadow-run` | 复制真实请求到目标系统并隔离副作用，比较响应、意图、Trace 和性能。 |
| `live-event-replay` | 重放实时或历史事件流，保持顺序、时间、幂等和外部响应。 |
| `side-effect-suppression` | 将支付、消息、邮件、写库和不可逆调用转换为安全意图记录或影子目标。 |
| `dual-write-validation` | 验证源目标双写一致性、冲突、顺序、补偿和回收策略。 |
| `canary-traffic-planner` | 选择低风险租户、用户、接口和流量比例设计 Canary 阶段。 |
| `progressive-cutover` | 按模块、流量、租户或能力逐步切换并验证每级门槛。 |
| `automatic-rollback` | 根据错误、差异、延迟、数据和业务 SLI 自动触发安全回滚。 |
| `migration-wave-planner` | 按依赖、风险、价值、团队和维护窗口组织迁移波次。 |
| `strangler-routing` | 在网关、服务、消息或前端路由层按能力分流旧实现和新实现。 |
| `post-cutover-monitoring` | 切换后持续监控差异、异常、性能、数据质量、回滚条件和学习项。 |

## Batch outputs

- `batch-result.yaml`：批次状态、输入、产物和未解决项。
- `evidence-index.json`：所有子 Skill 证据索引。
- `semantic-loss-ledger.json`：不支持、近似、未验证与需人工语义。
- `next-actions.yaml`：下游 Batch、升级、试点或阻断建议。

## Orchestration constraints

- 子 Skill 可并行执行，但存在数据依赖时必须按 `catalog.yaml` 顺序或任务图执行。
- 所有模型输出都只是候选，必须经过本 Batch 对应的客观工具门禁。
- 任一阻断项不得被平均分或整体“高相似度”覆盖。
