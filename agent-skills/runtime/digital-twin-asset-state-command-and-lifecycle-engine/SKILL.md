---
name: digital-twin-asset-state-command-and-lifecycle-engine
description: 建立物理资产、设备、Twin、状态、命令、关系、Policy和生命周期的一致模型。
---

# Digital Twin

## Twin层级

Enterprise
Site
Line
Cell
Asset
Component
Device

## State

REPORTED
DESIRED
OBSERVED
CALCULATED
PREDICTED
MANUAL_OVERRIDE
STALE
UNKNOWN

## State字段

Value
Quality
Source Time
Receive Time
Source
Version
Confidence
Expiry

## Desired State

必须记录：

Requested
Accepted
Delivered
Applied
Rejected
Expired
Rolled Back

不能把：
