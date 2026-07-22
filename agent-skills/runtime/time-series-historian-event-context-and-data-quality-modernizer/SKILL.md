---
name: time-series-historian-event-context-and-data-quality-modernizer
description: 现代化Historian、时序信号、事件、报警、上下文、压缩、保留和工业数据质量。
---

# Industrial Time Series

## Signal

Measurement
State
Counter
Energy
Setpoint
Command
Alarm
Quality
Derived
Prediction

## Point

Value
Quality
Source Timestamp
Gateway Timestamp
Ingest Timestamp
Sequence
Device
Tag Version

## Sampling

PERIODIC
CHANGE_OF_VALUE
DEADBAND
EVENT
BURST
MANUAL
CALCULATED

## 数据质量

Completeness
Freshness
Validity
Range
Rate of Change
Flatline
Spike
Duplicate
Out of Order
Clock Drift
Quality Flag
Gap

## Historian

记录：

Compression
Deadband
Interpolation
Retention
Archive
Backfill
Query
Time Zone
Daylight Saving
Clock Source

## 时间同步

来源：

DEVICE_CLOCK
PLC_CLOCK
EDGE_CLOCK
PTP
NTP
GPS
CLOUD_CLOCK
UNKNOWN

## Event Context

Alarm或事件关联：

Asset
Process State
Production Order
Batch
Recipe
Operator
Maintenance
Shift
Model Version

## Raw与Contextualized

RAW_SIGNAL
CLEAN_SIGNAL
CONTEXTUALIZED_SIGNAL
AGGREGATE
FEATURE

不能覆盖Raw Evidence。

## Backfill

记录：

Range
Source
Ordering
Duplicate Policy
Quality
Checkpoint
Target

## 验收标准

- Source Time完整；
- Quality Flag不丢失；
- Historian压缩语义可见；
- Clock Drift可检测；
- Raw和Clean数据分开；
- Alarm有工艺上下文；
- Backfill可重放和核对。
