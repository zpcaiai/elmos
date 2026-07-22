---
name: dataset-label-lineage-quality-and-ai-data-governance
description: 管理训练、验证、评测和反馈Dataset的版本、标签、许可、血缘、质量、偏差和删除。
---

# AI Data Governance

## Dataset类型

TRAINING
VALIDATION
TEST
EVALUATION
CALIBRATION
RED_TEAM
HUMAN_FEEDBACK
PRODUCTION_SAMPLE
SYNTHETIC
REPLAY

## Dataset Version

绑定：

Source Snapshot
Query
Time Range
Filter
Sampling
Transformation
Label Version
Schema
Hash
Owner
Purpose

## Data Split

记录：

Train
Validation
Test
Holdout
Temporal Holdout
Geographic Holdout
Group Holdout

防止：

DATA_LEAKAGE
DUPLICATE_LEAKAGE
FUTURE_LEAKAGE
ENTITY_LEAKAGE
LABEL_LEAKAGE

## Label

记录：

Label Definition
Instruction
Annotator
Consensus
Disagreement
Confidence
Adjudication
Version

## Quality

Completeness
Validity
Label Accuracy
Noise
Class Balance
Coverage
Freshness
Representativeness
Duplicate
Outlier

## Data Rights

记录：

Source
License
Consent／Policy Reference
Permitted Purpose
Prohibited Use
Retention
Deletion
Redistribution
Model Training Permission

## Deletion

沿血缘影响：

Dataset
Feature
Checkpoint
Model
Embedding
Index
Evaluation
Fine-tune
Derived Artifact

## 验收标准

- Dataset可重建；
- Split防止泄漏；
- Label指令版本化；
- Ground Truth有质量；
- 使用目的明确；
- 数据删除沿AI Lineage传播；
- Dataset问题阻止模型晋级。
