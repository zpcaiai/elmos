# Batch 23：Cross-Business Journey、Saga与逻辑闭环

## Goal

验证跨域、跨服务、跨Provider的完整Journey、Saga、Partial Success、Unknown Outcome与人工恢复。

## Inputs

- Business-line packs；
- Service/data/message topology；
- Provider contracts；

## Outputs

- Cross-domain journey IR；
- Saga/compensation plans；
- Journey tests/replay；
- Journey certificates；

## Execution Flow

1. 定义Entry/Exit和Correlation；
2. 编排跨域状态机；
3. 处理Timeout/Retry/Duplicate/Abandonment；
4. 生成补偿和人工终态；
5. 运行Golden/Fault/Mutation/Replay；

## Verification

- 单Service成功不误报Journey成功；
- Unknown Outcome可查询/恢复；
- 跨版本Journey通过；

## Stop Conditions

- Saga无补偿或终态；
- 跨域Context丢失；
- Provider回调无法对账；

## Gate

`Cross-Business Journey Gate`

## Installable Skill

`agent-skills/runtime/b23-cross-business-journey-closure/SKILL.md`
