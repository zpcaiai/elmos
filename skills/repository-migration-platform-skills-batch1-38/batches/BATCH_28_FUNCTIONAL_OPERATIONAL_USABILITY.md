# Batch 28：Functional Usability与Operational Usability

## Goal

保证用户、管理员、开发者和运维人员能够真实发现、完成、恢复和诊断所有关键任务。

## Inputs

- Capabilities/journeys；
- UI/CLI/API；
- Error/permission states；
- Accessibility/localization requirements；

## Outputs

- Usability test packs；
- State coverage matrix；
- CLI/API usability assets；
- Operational diagnostics；

## Execution Flow

1. 验证导航和入口；
2. 覆盖Form/Loading/Empty/Error/Retry/Cancel/Permission/Partial states；
3. 验证Accessibility/i18n/browser；
4. 验证CLI Dry-run/exit codes；
5. 验证Alert和Runbook可发现；

## Verification

- P0任务可被目标角色独立完成；
- 错误信息可行动；
- 危险动作不可误触；
- 关键流程可键盘/辅助技术使用；

## Stop Conditions

- 功能存在但无入口；
- 错误状态无限等待；
- 运维只能靠源码排障；

## Gate

`Usability Closure Gate`

## Installable Skill

`agent-skills/runtime/b28-functional-operational-usability/SKILL.md`
