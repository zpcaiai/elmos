# Batch 18：Complete Project Generation Standard

## Goal

从Target Blueprint生成完整源码、Build、Config、依赖、基础设施、验证、运维、文档与一键生命周期。

## Inputs

- Target Blueprint；
- Generator packs；
- Project templates；
- Deployment/security profiles；

## Outputs

- Complete Project Manifest；
- Complete repositories；
- CI/CD/tests/proofs；
- Runbooks/docs；
- One-click lifecycle；
- CP1–CP5；

## Execution Flow

1. 解析完整项目Manifest；
2. 选择Repository templates；
3. 生成源码/Build/Config/DB/Message/API/Deployment；
4. 生成Test/Fuzz/Mutation/Proof；
5. 生成Observability/Security/Runbook/Docs；
6. 全生命周期验收；

## Verification

- Clean environment可Bootstrap/Build/Start/Test/Deploy/Rollback；
- 关键Placeholder为零；
- Backup有Restore测试；
- 文档命令可执行；

## Stop Conditions

- 隐藏人工步骤；
- 只有应用回滚；
- Critical alert无Runbook；

## Gate

`CP1–CP5`

## Installable Skill

`agent-skills/runtime/b18-complete-project-generation/SKILL.md`
