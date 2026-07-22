---
name: cloud-edge-sync-buffering-command-and-consistency-controller
description: 管理云边数据缓存、断点续传、命令队列、状态同步、冲突和离线一致性。
---

# Cloud-edge Coordination

## 数据方向

DEVICE_TO_EDGE
EDGE_TO_CLOUD
CLOUD_TO_EDGE
EDGE_TO_DEVICE
SITE_TO_SITE

## 数据类型

TELEMETRY
STATE
COMMAND
CONFIG
MODEL
FIRMWARE
EVENT
ALARM
AUDIT

## Buffer

记录：

Capacity
Disk
Priority
Retention
Compression
Encryption
Checkpoint
Oldest Record
Overflow Policy

## Overflow Policy

DROP_OLDEST_LOW_PRIORITY
DROP_NEW_LOW_PRIORITY
AGGREGATE
SAMPLE
PAUSE_SOURCE
ALARM
FAIL_CLOSED

Critical Alarm和Audit默认不得静默丢弃。

## Sync

AT_MOST_ONCE
AT_LEAST_ONCE
IDEMPOTENT
ORDERED_BY_ASSET
BEST_EFFORT
SNAPSHOT_AND_DELTA

## Conflict

DESIRED_STATE_CONFLICT
CONFIG_VERSION_CONFLICT
COMMAND_DUPLICATE
OUT_OF_ORDER
DEVICE_REPLACED
CLOCK_CONFLICT
MODEL_VERSION_CONFLICT

## Command

云端命令包含：

Command ID
Target
Precondition
Deadline
Expected Version
Approval
Idempotency
Ack Policy

## Offline

断网期间：

- 本地控制继续；
- 命令可能排队；
- 已过Deadline命令丢弃；
- 高风险命令不延迟执行；
- 数据恢复后顺序同步。

## Consistency

STRONG_LOCAL
EVENTUAL_CLOUD
LAST_WRITER_WITH_VERSION
DEVICE_AUTHORITY
EDGE_AUTHORITY
CLOUD_AUTHORITY
MANUAL_RECONCILIATION

## 验收标准

- Buffer有容量和Overflow策略；
- Critical数据不静默丢失；
- Command有Deadline；
- Duplicate可识别；
- 权威状态明确；
- 离线恢复可重放；
- 过期命令不会恢复后突然执行。
