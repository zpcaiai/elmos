# P01 验收与完成门

## 1. 完成定义

Agent 只能提交 `completion requested`。Gate Engine 校验以下条件后才能写 `COMPLETED`：

- [ ] 至少 native Adapter 与一个外部 Harness Adapter 通过 100% conformance tests。
- [ ] Session replay 对已认证事件产生相同的模型输入和策略快照。
- [ ] 硬拒绝策略、凭据隔离和沙箱逃逸红队无 Critical/High 未解决项。
- [ ] 所有工具失败均产生规范化错误和可审计事件，不出现悬挂 running 状态。
- [ ] Headless API/SDK 与 Web/CLI 客户端共享同一状态语义。

## 2. 必需证据

- [ ] immutable source/target/config/model/tool/environment revisions
- [ ] Requirement/Capability Ledger snapshot
- [ ] build/static/test/differential/nonfunctional results
- [ ] security/data-policy/permission/sandbox decisions
- [ ] cost/token/ETA and retry/fallback trace
- [ ] known gaps, waivers, residual risks and rollback evidence

## 3. Gate 结果

- `pass`：所有 required gates 通过，无未处理 Critical blocker。
- `fail`：实现或质量不满足，进入 diagnosis/repair。
- `blocked`：缺外部访问、不可获得源行为、需人工语义决策等真实 blocker。
- `waived`：只对明确非 Critical 项，需 owner、理由、补偿、expiry、审批和客户可见残余风险。

## 4. Freshness

代码、配置、规则、模型、环境或测试发生相关变化后，旧证据自动 stale；Gate 必须重算影响闭包。证据不得跨 source/target revision 混用。

## 5. 商业发布分级

| 等级 | 含义 | 最低要求 |
| --- | --- | --- |
| E1 | 可构建原型 | Build + 基础 smoke + 明确 gap。 |
| E2 | 功能内部测试 | 主要需求/能力闭环、unit/integration。 |
| E3 | 行为验证 Beta | 合同/差分/E2E、关键 unknown gap=0。 |
| E4 | 生产候选 | 性能/安全/韧性/迁移/回滚/观测。 |
| E5 | 认证生产交付 | 客户场景验收、SLA/DR/审计、长期监控与证据签名。 |

对外宣传必须注明具体场景、版本与认证等级。
