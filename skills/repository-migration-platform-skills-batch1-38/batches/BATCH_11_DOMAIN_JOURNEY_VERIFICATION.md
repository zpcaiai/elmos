# Batch 11：Domain Packs与Full-Stack Journey Verification

## Goal

为金融、电商、物流、医疗、工业、能源、身份、SaaS和Agentic AI建立领域不变量与全栈Journey验证。

## Inputs

- Domain model；
- Business rules；
- Critical journeys；
- Provider contracts；

## Outputs

- 9 Domain Packs；
- Journey runtime；
- Cross-layer oracles；
- Domain mutations；
- DV1–DV5；

## Execution Flow

1. 建立领域词汇和状态机；
2. 定义零容忍不变量；
3. 生成跨服务Journey；
4. 注入业务故障与恢复；
5. 验证隐私、安全、性能和版本兼容；

## Verification

- 金额不平/超卖/患者串档/设备越界/跨租户为零；
- Journey状态和Effect完整；
- 人工终态可处理；
- 领域Owner审批；

## Stop Conditions

- 领域规则冲突；
- Source行为违反真实业务要求；
- 关键Journey不可观察；

## Gate

`DV1–DV5`

## Installable Skill

`agent-skills/runtime/b11-domain-journey-verification/SKILL.md`
