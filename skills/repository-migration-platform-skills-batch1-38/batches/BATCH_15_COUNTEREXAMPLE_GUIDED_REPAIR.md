# Batch 15：Counterexample-Guided Repair与自演进验证

## Goal

统一差分、Mutation、Fuzz、SMT、模型检查、Lean和生产反例，定位根因并安全生成Patch、Rule与验证补强。

## Inputs

- Counterexamples；
- Artifacts/rules/tests；
- Historical repairs；
- Governance policy；

## Outputs

- Unified counterexample IR；
- Root-cause graph；
- Repair candidates；
- Transformation rules；
- Regression/Oracle/Mutation additions；
- CR1–CR5；

## Execution Flow

1. 规范化与最小化反例；
2. 独立复现；
3. 因果切片和根因定位；
4. 生成多种Repair候选；
5. Candidate arena竞争；
6. 独立验证；
7. 规则泛化与历史重扫；

## Verification

- 旧错误版本必须被Regression捕获；
- Critical repair零安全回归；
- Rule有负例和适用前提；
- 自演进不可降低标准；

## Stop Conditions

- 无法确认真实反例；
- Patch只修字面样例；
- Oracle/Theorem被弱化；

## Gate

`CR1–CR5`

## Installable Skill

`agent-skills/runtime/b15-counterexample-guided-repair/SKILL.md`
