---
name: evidence-provenance-lineage-and-temporal-truth-engine
description: "管理Claim、Evidence、来源、血缘、双时间、签名、撤回和证据可信度。"
---

# Evidence Fabric

## Claim

Subject
Predicate
Object
Source
Authority
Confidence
Valid Time
Transaction Time
Evidence

## Evidence类型

SOURCE
RUNTIME
TEST
HUMAN_DECISION
FINANCIAL
POLICY
SIMULATION
OBSERVATION
THIRD_PARTY
DERIVED

## Provenance

映射：

Entity
Activity
Agent
Used
Generated
Derived
Attributed

## Lineage

数据任务映射：

Job
Run
Dataset
Input
Output
Facet

## 双时间

Valid From / Until
Observed At
Recorded At
Superseded At

## Correction

错误Evidence通过：

RETRACT
SUPERSEDE
CORRECT
INVALIDATE

处理，不覆盖历史。

## Evidence状态

VALID
STALE
CONFLICTED
RETRACTED
SUPERSEDED
UNVERIFIED
INVALID

## Integrity

保存：

Hash
Signature
Signer
Transparency Reference
Storage Reference
Retention

## 验收标准

- Claim和Evidence分开；
- 支持双时间；
- 来源可追踪；
- Derived Claim可解释；
- 修正不删除历史；
- Evidence可签名验证；
- 过期Evidence不用于当前决策。
