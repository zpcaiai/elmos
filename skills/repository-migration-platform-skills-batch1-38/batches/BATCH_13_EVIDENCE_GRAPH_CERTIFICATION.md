# Batch 13：Evidence Graph、独立裁判、红队与持续认证

## Goal

建立不可变Artifact–Execution–Finding–Certificate Lineage、Builder/Verifier隔离、CA与持续撤销治理。

## Inputs

- Artifacts/executions/findings；
- Verifier runtimes；
- Oracle registry；
- Certificate policies；

## Outputs

- Immutable evidence graph；
- Independent replay bundles；
- CA/transparency log；
- Red-team reports；
- EA1–EA5；

## Execution Flow

1. 内容寻址保存Evidence；
2. 建立完整Lineage；
3. 隔离Builder/Verifier/CA；
4. 独立Oracle和重放；
5. 签发/降级/撤销证书；
6. 历史Release重扫；

## Verification

- Critical evidence均签名；
- 角色冲突为零；
- Scope/Assumption完整；
- 伪造或过期证书不可用；

## Stop Conditions

- Evidence可被覆盖；
- Builder自证；
- Critical冲突未冻结；

## Gate

`EA1–EA5`

## Installable Skill

`agent-skills/runtime/b13-evidence-graph-certification/SKILL.md`
