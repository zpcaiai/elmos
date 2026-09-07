# Batch 19：90路径Executable Generator Packs

## Goal

把90条有向路径实现为可安装、执行、测试、签名和认证的完整项目Generator Packs。

## Inputs

- Complete Project Blueprint；
- Source repositories；
- Path rules；
- Framework/dependency profiles；

## Outputs

- 90 executable packs；
- Path lowerings；
- Idiomatic target projects；
- Golden/Hidden corpora；
- Benchmarks；
- GP1–GP5；

## Execution Flow

1. 解析Source AST/IR；
2. 执行Path-specific lowering；
3. 装配Framework/Dependency；
4. 生成Target AST和惯用代码；
5. 生成完整项目；
6. 运行Golden/Hidden/Adversarial/历史基准；
7. 签名发布；

## Verification

- 90个独立Pack；
- Target reparse和Semantic roundtrip；
- Hidden项目通过；
- 关键语义/完整性Floor通过；

## Stop Conditions

- Pack仅为Prompt/文本替换；
- 未声明语义静默丢弃；
- 无Hidden评估；

## Gate

`GP1–GP5`

## Installable Skill

`agent-skills/runtime/b19-executable-generator-packs/SKILL.md`
