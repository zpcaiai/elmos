---
name: industrial-protocol-tag-semantic-and-asset-model
description: 将寄存器、PLC变量、SCADA Tag和设备Telemetry转换为版本化工业语义和资产模型。
---

# Industrial Semantic Model

## Tag Contract

Asset
Signal
Source Endpoint
Protocol Address
Data Type
Engineering Unit
Scale
Range
Quality
Timestamp
Sampling
Deadband
Read / Write
Safety Classification
Owner

## Tag类型

MEASUREMENT
STATE
COMMAND
SETPOINT
ALARM
COUNTER
ENERGY
QUALITY
CALCULATED
DIAGNOSTIC

## Quality

GOOD
UNCERTAIN
BAD
STALE
SUBSTITUTED
MANUAL
SIMULATED
UNKNOWN

## Time

SOURCE_TIME
DEVICE_TIME
PLC_SCAN_TIME
GATEWAY_TIME
EDGE_RECEIVE_TIME
CLOUD_RECEIVE_TIME

必须保留多个时间，而不是只覆盖为云接收时间。

## Engineering Unit

记录：

Unit
Scale
Offset
Precision
Valid Range
Alarm Range

## Write Policy

READ_ONLY
ADVISORY_ONLY
AUTHORIZED_WRITE
SEQUENCED_WRITE
INTERLOCKED_WRITE
SAFETY_PROHIBITED

## Canonical Asset

Asset Class
Asset Instance
Component
Signal
Command
Event
Relationship
Lifecycle

## Mapping状态

LOSSLESS
SEMANTICALLY_COMPATIBLE
SCALE_TRANSFORMED
QUALITY_REDUCED
TIME_REDUCED
WRITE_RESTRICTED
LOSSY_APPROVED
UNKNOWN

## 验收标准

- Raw Address不作为最终Contract；
- Unit和Scale明确；
- Quality不会被丢弃；
- Source Time可追踪；
- Write Tag单独治理；
- Safety Classification进入Hard Gate；
- Mapping有兼容等级。
