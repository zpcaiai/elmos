# Batch 22：Business-Line Functional Closure Packs

## Goal

为每条真实业务线建立对象、命令、查询、事件、状态机、审批、撤销、补偿、管理和报表闭环。

## Inputs

- Capability registry；
- Business vocabulary；
- Domain rules；
- Admin requirements；

## Outputs

- Business-line manifests；
- State machines；
- Command/query/event registries；
- Admin/test/runbook packs；

## Execution Flow

1. 定义Actors和对象；
2. 恢复Create/Read/Update/Cancel/Close/Expire等路径；
3. 定义计算/审批/时间规则；
4. 生成异常和人工处理；
5. 绑定数据/API/Admin/Test/Metric；

## Verification

- 每条业务线正常/异常/撤销/补偿闭环；
- 业务Owner审批；
- 关键对象终态可解释；

## Stop Conditions

- 只有Happy Path；
- 人工处理无终态；
- 管理端无法修复或查询；

## Gate

`Business-Line Closure Gate`

## Installable Skill

`agent-skills/runtime/b22-business-line-closure/SKILL.md`
