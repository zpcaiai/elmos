# Batch 36：Production Operations、Support与Service Management

## Goal

建立Service Catalog、SLO/Error Budget、On-call、Incident、Problem、Change、Support和持续健康评审。

## Inputs

- Production services；
- Owners/SLOs；
- Alerts/runbooks；
- Support channels；

## Outputs

- Service catalog；
- On-call/incident workflows；
- Support diagnostics；
- Operational health reviews；
- Operational certification；

## Execution Flow

1. 登记Service和Owner；
2. 定义SLI/SLO/SLA/Error Budget；
3. 配置Alert routing和Incident command；
4. 关联Support tickets与Trace；
5. 建立Known errors/Problem/Change management；
6. 周期容量/成本/安全/证书评审；

## Verification

- P0服务有Owner和On-call；
- Alert可行动；
- 客户问题可关联实际Release/Trace；
- 证书按期续期；

## Stop Conditions

- 无人负责服务；
- Alert风暴无Runbook；
- Support无法获取安全诊断包；

## Gate

`Production Operations Gate`

## Installable Skill

`agent-skills/runtime/b36-production-operations-support/SKILL.md`
