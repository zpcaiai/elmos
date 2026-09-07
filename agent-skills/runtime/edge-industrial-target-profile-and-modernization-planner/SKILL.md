---
name: edge-industrial-target-profile-and-modernization-planner
description: 为设备、PLC、SCADA、Historian和边缘系统选择保留、网关、升级、开放、边缘化、云化或替换路径。
---

# Target Strategy

## 候选

KEEP_AND_HARDEN
FIRMWARE_UPGRADE
PROTOCOL_GATEWAY
OPC_UA_ENABLE
MQTT_ENABLE
SPARKPLUG_ENABLE
EDGE_COMPUTE
DIGITAL_TWIN
HISTORIAN_MODERNIZE
CLOUD_INTEGRATION
EDGE_AI
CONTROLLER_REPLACEMENT
SCADA_REPLACEMENT
RETIRE

## 决策因素

Safety
Determinism
Latency
Availability
Offline Requirement
Protocol
Vendor Support
Lifecycle
Hardware
CPU / Memory
Network
Data Volume
Write Requirement
Cybersecurity
Maintenance Window
Skills
Cost

## 控制路径

不能因为设备支持云连接就将控制逻辑迁云。

每项目标声明：

CONTROL_LOCATION
FAIL_SAFE
OFFLINE_DURATION
COMMAND_AUTHORITY
ROLLBACK
HUMAN_OVERRIDE

## Wave

Wave 0：
只读资产、网络和Tag发现

Wave 1：
边缘采集、Historian和Digital Shadow

Wave 2：
Device Identity和观测

Wave 3：
OTA与Shadow AI

Wave 4：
Advisory和受控写

Wave 5：
单Cell／单Line闭环

Wave 6：
旧平台退役

## 验收标准

- Safety是Hard Constraint；
- 保留是正式目标；
- Control和Analytics分开；
- Offline能力进入决策；
- 写路径后于读路径；
- 旧设备可通过Gateway延寿；
- 无安全路径明确Blocked。
