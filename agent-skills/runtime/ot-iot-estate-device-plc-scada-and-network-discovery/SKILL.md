---
name: ot-iot-estate-device-plc-scada-and-network-discovery
description: 只读清点工厂、设备、PLC、SCADA、HMI、Historian、Edge和工业网络依赖。
---

# OT Estate Discovery

## 发现层级

Enterprise
→ Site
→ Area
→ Line
→ Cell
→ Asset
→ Device
→ Signal

## 设备类型

SENSOR
ACTUATOR
PLC
PAC
SAFETY_PLC
RTU
ROBOT
CNC
DRIVE
METER
CAMERA
GATEWAY
HMI
SCADA_SERVER
HISTORIAN
EDGE_NODE
ENGINEERING_STATION

## 发现来源

Engineering Project
PLC Export
SCADA Export
Historian
Network Switch
Asset Register
EAM / CMMS
MES
OPC Browse
MQTT Metadata
Passive Network Observation
Operator Confirmation

## Source与Runtime

关联：

Engineering Project
→ Downloaded Program
→ PLC Checksum
→ Runtime Task
→ Physical Asset

## 网络

记录：

Zone
Subnet
VLAN
Switch
Firewall
Conduit
Protocol
Direction
Endpoint
Latency
Redundancy

## 使用状态

ACTIVE
SEASONAL
STANDBY
SPARE
DECOMMISSIONED_PHYSICAL
UNKNOWN

## Findings

UNKNOWN_DEVICE
UNKNOWN_DEVICE_OWNER
PLC_PROJECT_RUNTIME_MISMATCH
UNMANAGED_ENGINEERING_STATION
FLAT_OT_NETWORK
PUBLICLY_REACHABLE_OT_DEVICE
SHARED_GATEWAY
UNSUPPORTED_FIRMWARE
UNKNOWN_SAFETY_DEPENDENCY
HISTORIAN_SOURCE_UNKNOWN

## 输出

ot-estate.json
physical-asset-graph.json
device-inventory.json
plc-runtime-map.json
scada-inventory.json
historian-inventory.json
ot-network-topology.json
ot-unknowns.json

## 验收标准

- Physical Asset和Device分开；
- PLC项目与Runtime校验；
- Passive Discovery优先；
- Safety设备单独分类；
- 网络关系具有方向；
- Unknown设备进入风险；
- 发现过程不影响生产流量。
