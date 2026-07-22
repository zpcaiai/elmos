---
name: training-platform-gpu-scheduling-checkpoint-and-capacity
description: 建立CPU／GPU训练平台、队列、优先级、分布式训练、Checkpoint、抢占和容量治理。
---

# Training Platform

## Workload

EXPERIMENT
TRAINING
HYPERPARAMETER_TUNING
FINE_TUNING
DISTILLATION
EVALUATION
EMBEDDING_BUILD
BATCH_INFERENCE

## Resource Profile

CPU
Memory
GPU Type
GPU Count
VRAM
Local Disk
Network
Runtime
Maximum Duration
Priority
Budget

## Queue

INTERACTIVE
STANDARD
BATCH
HIGH_PRIORITY
REGULATED
PREEMPTIBLE
DEDICATED

## Scheduling

考虑：

GPU Compatibility
Topology
Affinity
Gang Scheduling
Quota
Priority
Fair Share
Preemption
Cost
Data Locality

## Distributed Training

记录：

World Size
Rank
Backend
Network
Gradient Strategy
Sharding
Checkpoint
Elasticity
Failure Recovery

## Checkpoint策略

TIME_BASED
STEP_BASED
EPOCH_BASED
PREEMPTION_AWARE
MANUAL

## Spot／Preemptible

只有满足：

- Checkpoint；
- Resume；
- Data可重读；
- Side Effect幂等；

时才能使用。

## Capacity

预测：

GPU Hours
Peak Demand
Queue Time
Utilization
Fragmentation
Reservation
Failure
Growth

## 验收标准

- GPU类型进入Compatibility；
- Queue有公平策略；
- 分布式拓扑可追踪；
- 抢占前提明确；
- Checkpoint真实恢复；
- Capacity与Cost共同治理。
