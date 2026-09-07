---
name: experiment-tracking-training-pipeline-and-reproducibility
description: 管理实验、训练DAG、代码、数据、环境、参数、指标、Checkpoint和可重复性。
---

# Training Reproducibility

## Experiment Run

绑定：

Source Commit
Pipeline Version
Dataset Version
Feature Version
Environment
Dependency Lock
Container Digest
Hardware
Seed
Parameters
Metrics
Artifacts

## Pipeline Step

INGEST
VALIDATE_DATA
BUILD_FEATURES
TRAIN
TUNE
EVALUATE
EXPLAIN
PACKAGE
REGISTER
REPORT

## Reproducibility状态

BITWISE_REPRODUCIBLE
NUMERICALLY_REPRODUCIBLE
METRIC_REPRODUCIBLE
FUNCTIONALLY_REPRODUCIBLE
PARTIAL
UNREPRODUCIBLE

## Randomness

记录：

Language RNG
NumPy
Framework
Data Loader
Distributed Worker
Hash Seed
Sampler
Augmentation
Dropout

## Cache

Pipeline Cache Key必须包含：

Code
Data
Parameters
Environment
Component
Hardware Constraints

## Checkpoint

记录：

Step
Epoch
Global Step
Optimizer
Scheduler
Random State
Data Cursor
Distributed State

## Experiment Comparison

比较：

Metric
Confidence Interval
Dataset
Hardware
Runtime
Cost
Training Time
Model Size

## 验收标准

- Run绑定完整输入；
- Pipeline DAG版本化；
- Cache不跨错误Dataset；
- Checkpoint可恢复；
- Seed完整；
- Reproducibility定义明确；
- 实验不能直接成为生产Release。
