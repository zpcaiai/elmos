# Batch 35：Release、Go-Live与Production Acceptance

## Goal

把代码完成与允许上线分离，执行业务、数据、管理、安全、性能、可用性、运维、支持和回滚的统一Go/No-Go。

## Inputs

- Release candidate；
- Acceptance evidence；
- Certificates；
- Production environment；

## Outputs

- Release readiness report；
- Go/No-Go decision；
- Launch plan/hypercare；
- Production acceptance certificate；

## Execution Flow

1. 验证业务/Data/Admin/Security/Performance/HA；
2. 检查环境Parity/Config/Secret/DB/Message/Provider；
3. 验证Monitoring/Alert/Runbook/Backup/Rollback；
4. 执行UAT/OAT；
5. 由Decision Board审批；
6. Launch与Hypercare；

## Verification

- 所有P0/P1 Gate通过；
- 关键证书有效；
- 支持与On-call准备；
- 自动暂停/回滚可用；

## Stop Conditions

- 存在生产Blocker；
- 配置未冻结；
- 回滚/恢复未演练；

## Gate

`Production Acceptance Gate`

## Installable Skill

`agent-skills/runtime/b35-go-live-production-acceptance/SKILL.md`
