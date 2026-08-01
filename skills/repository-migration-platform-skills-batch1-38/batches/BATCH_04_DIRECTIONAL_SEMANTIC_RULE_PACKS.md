# Batch 04：90 Directional Semantic Rule、Mutation、Test与Certification Packs

## Goal

为10×9有向路径建立路径级类型、错误、并发、内存、框架与项目生成规则及验证包。

## Inputs

- Unified Semantic IR；
- Source/Target语言Profile；
- Target blueprint；
- Path constraints；

## Outputs

- 90 directional rule packs；
- Path-specific mutations/tests；
- Lowering manifests；
- DP1–DP5 certificates；

## Execution Flow

1. 建立每条路径规则Manifest；
2. 生成类型/错误/资源/并发映射；
3. 形成Negative examples与适用前提；
4. 运行Golden、Hidden、Mutation与差分；
5. 签发路径级证书；

## Verification

- 90条路径均有独立Manifest；
- Critical mutation存活为零；
- 逆向路径不自动继承；
- Scope与版本明确；

## Stop Conditions

- 关键语义无安全Lowering；
- 规则只在单一样例通过；
- Target权限或副作用扩大；

## Gate

`DP1–DP5`

## Installable Skill

`agent-skills/runtime/b04-directional-semantic-rule-packs/SKILL.md`
