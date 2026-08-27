# Credit and Billing Invariant Model

> Skill ID: `elmos-credit-billing-invariant-model`  
> Priority: **P0**  
> Domain: `platform`  
> Package: `elmos-formal-assurance-kernel-v1.0.0`

## 1. 业务目标

证明预充 token/credit 的预留、消费、退款、收入确认和事件去重在并发与故障下保持守恒。

该 Skill 属于 Elmos `Formal Assurance Plane`。它不把“测试通过”“没有找到反例”或“求解器超时”包装成完整证明；所有结论均必须携带证明模式、范围、假设、边界、可信基和可重放证据。

## 2. 触发条件

- 用户或 Golden Route 要求对 `platform` 产物提供形式化保证。
- ChangeGraph 判断相关规格、代码、Schema、运行时或依赖发生语义变化。
- P05/E1–E5 发布门要求重新计算关键证明义务。
- 运行时监控发现行为超出已证明模型或假设发生漂移。

## 3. 输入契约

- `billing ledger`
- `usage events`
- `reservation policy`

所有输入必须包含 tenant/account、source revision、semantic profile、criticality、provenance 和完整性摘要。缺少关键来源或版本时返回 `ASSUMPTION_REQUIRED` 或 `UNSUPPORTED`，不得推测后继续认证。

## 4. 输出契约

- `billing model`
- `invariant proof`
- `double-charge witness`

输出统一使用 `contracts/schemas/proof-result.schema.json`、`proof-artifact.schema.json` 和 `proof-coverage.schema.json`；机器结果是报告、UI 和发布门的唯一事实来源。

## 5. 证明方法

- conservation invariants
- idempotent ledger model
- serializability refinement

## 6. 必须保持的性质

- balance>=0
- 同一 usage_event_id 至多扣费一次
- reserved=consumed+refundable
- 终态任务的账务可对账

## 7. 执行流程

1. 解析输入并冻结 source/target/model/assumption/TCB 摘要。
2. 生成粒度最小且可组合的证明义务；标注安全性、活性、等价、终止或信息流类别。
3. 由 `elmos-verifier-portfolio-router` 选择证明器、模式、边界、超时和回退链。
4. 在 deny-by-default、secretless、资源受限的沙箱中执行。
5. 对证据、日志、证书和反例进行内容寻址提交；陈旧 fencing token 一律拒绝。
6. 将反例最小化并交给 `elmos-counterexample-to-test` 生成永久回归测试。
7. 聚合覆盖率，但保持最弱关键证据等级，不做状态膨胀。
8. 触发 Release Gate、报告和 Proof Drift 订阅。

## 8. 依赖

- `elmos-proof-obligation-planner`
- `elmos-verifier-portfolio-router`
- `elmos-tla-task-runtime-model`

## 9. 失败语义

- 证明被反驳：`REFUTED_WITH_COUNTEREXAMPLE`，必须保存可重放 witness。
- 在声明边界内无反例：`BOUNDED_NO_COUNTEREXAMPLE`，禁止显示为 `PROVED`。
- 超时或资源耗尽：分别为 `UNKNOWN_TIMEOUT` / `UNKNOWN_RESOURCE_LIMIT`。
- 语言、动态行为或工具不支持：`UNSUPPORTED`，进入显式边界或运行时监控。
- 依赖假设未确认：`ASSUMPTION_REQUIRED`。
- 第三方证明器异常、证据损坏、版本未固定：fail closed。

## 10. 安全与多租户

- 公式、源码片段、反例和日志默认视为租户机密。
- 外部证明器无网络、无 Secret、只读输入、临时可写工作区、硬 CPU/内存/时间限制。
- Artifact 以 tenant-scoped envelope encryption 保存；跨租户缓存默认禁用。
- Tool/adapter 调用必须记录 owner environment、permission profile、fencing token 和 trace ID。

## 11. 可观测性与 SLO

- `P95 orchestration overhead < 2 s excluding verifier runtime`。
- 指标至少包含 queue delay、solver wall-clock、cache hit、unknown rate、counterexample rate、evidence age 和 cost。
- 机器时长只使用 wall-clock seconds，不转换为人工人日。
- 所有 proof run 必须可从任务 Trace 跳转到义务、假设、TCB 和 Artifact。

## 12. 商业发布边界

此 Skill 的静态契约和参考实现通过，不等于已在真实 Elmos 主仓库或客户仓库完成生产认证。进入 `TRUSTED` 前仍需执行目标工具链、真实数据库/运行时、故障注入、性能压测、E1–E5 和 P05 门禁。
