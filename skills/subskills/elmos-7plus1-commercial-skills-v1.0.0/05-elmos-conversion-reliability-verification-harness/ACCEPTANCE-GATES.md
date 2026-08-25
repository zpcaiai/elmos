# P05 验收与完成门

## 1. 完成定义

Agent 只能提交 `completion requested`。Gate Engine 校验以下条件后才能写 `COMPLETED`：

- [ ] Requirement 与 Capability closure 达到策略阈值，Critical unknown gap=0。
- [ ] build/static/contract/differential/E2E/security 的 required gates 全部 pass。
- [ ] Critical/High mismatch、存活关键 mutation、未处理严重漏洞为 0。
- [ ] TODO/stub/mock/unsupported 均被计算并符合政策；不得隐藏。
- [ ] 证据 freshness、source/target revision、environment 与工具版本一致。
- [ ] 所有 waiver 未过期并有正式审批与补偿控制。

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
