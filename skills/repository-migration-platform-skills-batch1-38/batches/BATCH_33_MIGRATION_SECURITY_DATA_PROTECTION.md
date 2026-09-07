# Batch 33：Migration Security与Data Protection Assurance

## Goal

保护Snapshot、Replay、Shadow、CDC、Backfill、Dual-run、Cutover和Source退休期间扩大的攻击面。

## Inputs

- Migration plan；
- Data/security classifications；
- Worker/tool/skill profiles；
- Production credentials；

## Outputs

- Migration threat model；
- Security controls/tests；
- Audit and incident plans；
- Migration security certificate；

## Execution Flow

1. 建模迁移攻击面；
2. 隔离Replay/Shadow数据；
3. 统一Source/Target身份和权限；
4. 限制Backfill/CDC/Schema权限；
5. 签名迁移Artifacts；
6. 验证Cutover/Rollback审批；
7. 撤销Source凭证；

## Verification

- 迁移临时环境不含明文生产Secret；
- 权限Parity通过；
- 跨Tenant迁移为零；
- 所有高风险操作有Audit；

## Stop Conditions

- Replay环境可外联泄露数据；
- Dual-run权限不一致；
- Source凭证无法撤销；

## Gate

`Migration Security Gate`

## Installable Skill

`agent-skills/runtime/b33-migration-security-data-protection/SKILL.md`
