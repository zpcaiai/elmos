---
name: edge-runtime-container-orchestration-and-offline-autonomy
description: 管理边缘节点、运行时、容器、离线配置、资源、升级、Local Registry和自治能力。
---

# Edge Runtime

## Edge Node

Industrial PC
Gateway
Server
Embedded Linux
Windows Edge
ARM Device
GPU Edge
NPU Edge

## Runtime

BARE_PROCESS
SYSTEM_SERVICE
CONTAINER
EDGE_KUBERNETES
KUBEEDGE_PROVIDER
VM
VENDOR_RUNTIME

## Workload类型

PROTOCOL_ADAPTER
BUFFER
RULE
AI_INFERENCE
TWIN
LOCAL_UI
HISTORIAN
SYNC
OBSERVABILITY
OTA_AGENT

## 离线等级

CLOUD_REQUIRED
SHORT_DISCONNECT
HOURS_AUTONOMY
DAYS_AUTONOMY
FULL_LOCAL_OPERATION

## 离线资产

Configuration
Policy
Certificate
Workload Artifact
Model
Schema
Twin Cache
Command Queue
Data Buffer
Runbook

## Local Registry

断网期间更新可能需要：

- 本地Artifact Registry；
- 固件缓存；
- 模型缓存；
- 镜像签名验证；
- Dependency Bundle。

## Resource

CPU
Memory
Disk
GPU
Temperature
Power
Network
Storage Wear

## Watchdog

检测：

Process
Container
Disk Full
High Temperature
Memory
Broker
Protocol
Cloud Link
Certificate

## Fail Safe

边缘工作负载失败时：

- 本地PLC继续；
- Command停止；
- 最后安全配置；
- Alarm；
- Operator Handoff；
- 本地恢复。

## 验收标准

- 边缘不依赖持续云连接；
- Runtime支持签名Artifact；
- 资源和温度可监控；
- Disk Full有策略；
- 云断网不影响安全控制；
- 配置有Local Version；
- Edge节点可以恢复和重建。
