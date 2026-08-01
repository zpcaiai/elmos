# Batch 37：Post-Migration Stabilization与Source Retirement Closure

## Goal

在Target稳定后检测所有隐藏Source caller、写入、Job、Consumer、Credential和Provider回调并安全退出Source。

## Inputs

- Cutover state；
- Traffic/caller telemetry；
- Final reconciliation；
- Archive/retention policies；

## Outputs

- Stability report；
- Source caller inventory；
- Final reconciliation；
- Retirement/archival evidence；
- Retirement certificate；

## Execution Flow

1. 等待稳定窗口；
2. 验证Target Primary；
3. 监测Source流量/写/Job/Consumer/Callback/Credential；
4. 执行最终数据/消息/Provider对账；
5. Source只读/Scale-to-zero；
6. 撤销凭证和删除基础设施；
7. 持续退休后监控；

## Verification

- 未知Source caller为零；
- Source生产Credential为零；
- 最终对账通过；
- Archive可恢复；
- Rollback窗口正式关闭；

## Stop Conditions

- 季度/应急Caller未覆盖；
- Source仍可写；
- Target无法理解退休窗口数据；

## Gate

`Source Retirement Gate`

## Installable Skill

`agent-skills/runtime/b37-source-retirement-closure/SKILL.md`
