# Batch 06：Dependency、Native、License与Supply-Chain Graph

## Goal

按实际Usage Contract迁移依赖，处理组合替代、Native资产、License、SBOM、签名与供应链风险。

## Inputs

- Dependency graph；
- Usage slices；
- Target ecosystems；
- License/security policies；

## Outputs

- Dependency replacement plans；
- SBOM/provenance；
- Native asset plan；
- License report；
- DA/DR evidence；

## Execution Flow

1. 提取实际API使用切片；
2. 评估Direct/Composite/Adapter/Service replacement；
3. 锁定版本和Feature；
4. 生成SBOM/License/Provenance；
5. 运行替代契约与供应链验证；

## Verification

- 依赖闭包可解析；
- 未知Native binary为零；
- License冲突为零；
- Critical组件有签名和来源；

## Stop Conditions

- 无安全替代且不可保留；
- License阻断；
- 恶意或来源不明组件；

## Gate

`DA/DR Certification`

## Installable Skill

`agent-skills/runtime/b06-dependency-supply-chain-graph/SKILL.md`
