# Batch 14：Formal Verification与Proof-Carrying Migration

## Goal

用Formal IR、SMT、Symbolic Execution、Model Checking与Lean证明关键属性，并绑定实际代码与Artifact。

## Inputs

- Semantic IR；
- Domain properties；
- Source/Target artifacts；
- Toolchains；

## Outputs

- Formal IR；
- Operational/state-machine semantics；
- Proof obligations；
- Lean proofs/kernel results；
- PCA/PCM；
- F1–F5；

## Execution Flow

1. 选择Property与Scope；
2. 编译Formal IR；
3. 运行SMT/符号执行/模型检查；
4. 生成Lean Specification；
5. Leanstral生成候选；
6. Lean Kernel检查；
7. 绑定代码和运行假设；

## Verification

- UNKNOWN不当PASS；
- Bound显式披露；
- sorry/admit为零；
- Proof→IR→Code→Artifact完整；

## Stop Conditions

- Theorem被弱化；
- 关键真实反例与Proof冲突；
- Binding断裂；

## Gate

`F1–F5`

## Installable Skill

`agent-skills/runtime/b14-formal-proof-carrying-migration/SKILL.md`
