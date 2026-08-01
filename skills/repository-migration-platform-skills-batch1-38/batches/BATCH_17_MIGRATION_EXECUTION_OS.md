# Batch 17：Migration Execution OS

## Goal

将迁移DAG执行为可暂停、恢复、取消、重放的Durable Workflows，并治理Worker、Model、Tool、Sandbox、成本与副作用。

## Inputs

- Executable migration plan；
- Task graph；
- Skill/tool/model registries；
- Budgets/policies；

## Outputs

- Workflow histories；
- Checkpoints；
- Worker leases；
- Approval records；
- Effect ledger；
- Artifact/evidence commits；
- MX1–MX5；

## Execution Flow

1. 编译Task Graph；
2. 实例化Durable Workflow；
3. 调度分布式Worker/Model/Tool；
4. Sandbox执行；
5. Checkpoint/Pause/Resume/Cancel；
6. 审批与证书Gate；
7. 多Repo/多Wave执行；

## Verification

- Lease/Fencing有效；
- History可确定重放；
- 非幂等Effect不自动Retry；
- 长任务跨Worker恢复；
- 预算不降低质量；

## Stop Conditions

- Split brain；
- 旧Attempt可提交；
- 取消后仍有未授权Effect；
- 过期Approval/Certificate被接受；

## Gate

`MX1–MX5`

## Installable Skill

`agent-skills/runtime/b17-migration-execution-os/SKILL.md`
