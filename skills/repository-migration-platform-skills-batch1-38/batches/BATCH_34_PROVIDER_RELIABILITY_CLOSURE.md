# Batch 34：External Integration与Provider Reliability Closure

## Goal

为支付、身份、短信、邮件、物流、AI模型、设备等Provider建立契约、Sandbox、Webhook、幂等、对账、Failover和成本闭环。

## Inputs

- Provider inventory/contracts；
- Credentials；
- Callbacks；
- SLA/cost requirements；

## Outputs

- Provider profiles/simulators；
- Contract/fault tests；
- Reconciliation/compensation；
- Provider runbooks/certificates；

## Execution Flow

1. 登记Provider能力和版本；
2. 生成Sandbox/Simulator；
3. 验证Auth/Timeout/Retry/Rate/Quota；
4. 验证Webhook签名/重放/顺序；
5. 处理Unknown outcome/对账/补偿；
6. 配置多Provider failover；

## Verification

- 不可逆Effect有幂等和Receipt；
- Callback可去重；
- Provider Drift可检测；
- Fallback不扩大权限；

## Stop Conditions

- Provider无Sandbox且无法安全测试；
- 回调身份不可验证；
- 对账数据不足；

## Gate

`Provider Reliability Gate`

## Installable Skill

`agent-skills/runtime/b34-provider-reliability-closure/SKILL.md`
