# Batch 05：Framework Adapter与Framework Combination Matrix

## Goal

恢复并迁移DI、Middleware、Security、Transaction、ORM、Lifecycle、Job与Streaming等Framework语义。

## Inputs

- Source/Target framework facts；
- Semantic IR；
- Framework versions；
- Target architecture；

## Outputs

- Framework IR；
- Source adapters；
- Target generators；
- Combination matrix；
- FA certification evidence；

## Execution Flow

1. 识别Source framework默认行为；
2. 抽取Framework facts；
3. 映射到Framework-neutral IR；
4. 生成Target组合；
5. 运行Lifecycle/Security/Transaction测试；

## Verification

- 声明组合均有Golden与Hidden；
- DI Scope和Middleware order正确；
- Security与Transaction不弱化；
- 版本矩阵完整；

## Stop Conditions

- 隐藏默认行为无法建模；
- 组合缺少运行证据；
- Framework重构改变业务语义；

## Gate

`FA1–FA5`

## Installable Skill

`agent-skills/runtime/b05-framework-adapter-matrix/SKILL.md`
