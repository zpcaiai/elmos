---
name: scenario-option-tradeoff-and-architecture-evaluation-engine
description: 对多个架构选项执行场景、质量属性、成本、风险、可逆性和Trade-off评估。
---

# Architecture Evaluation

## Option

每个重大决策至少比较：

BASELINE_KEEP
INCREMENTAL_MODERNIZE
TARGET_PLATFORM
ALTERNATIVE_PLATFORM
BUILD
BUY
HYBRID
RETIRE

不要求所有简单Decision强制生成大量虚假选项。

## Evaluation Scenario

Source
Stimulus
Environment
Artifact
Response
Response Measure

## Quality Attribute

AVAILABILITY
PERFORMANCE
SECURITY
MODIFIABILITY
INTEROPERABILITY
SCALABILITY
RECOVERABILITY
USABILITY
OPERABILITY
PORTABILITY
COST
SUSTAINABILITY
SAFETY

## Criteria

Weight
Threshold
Evidence
Confidence
Owner

## Trade-off

例如：

Lower Cost
↔ Lower Portability

Higher Consistency
↔ Higher Latency

Managed Service
↔ Vendor Binding

## 可逆性

REVERSIBLE
REVERSIBLE_WITH_COST
PARTIALLY_REVERSIBLE
IRREVERSIBLE
UNKNOWN

## Scenario Test

MODEL
PROTOTYPE
BENCHMARK
PILOT
SIMULATION
PRODUCTION_EVIDENCE
EXPERT_JUDGMENT

## Decision状态

PROMISING
VIABLE
VIABLE_WITH_CONTROLS
NOT_VIABLE
INCONCLUSIVE

## 验收标准

- 至少存在Baseline；
- Criteria有Owner；
- Trade-off显式；
- 不确定性可见；
- 可逆性进入Decision；
- Vendor声明不代替Evidence；
- Inconclusive不自动选最高分；
- Pilot结果可反馈。
