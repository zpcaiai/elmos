---
name: edge-iot-elmos-unified-evidence-integration
description: 将设备、PLC、协议、Twin、OTA、时序数据、Edge AI和不停产Cutover映射到ELMOS统一Evidence。
---

# Unified Integration

## Extension

{
  "scope": "EDGE_IOT_INDUSTRIAL",
  "engine": "ELMOS_EDGE_IOT_INDUSTRIAL",
  "engineExtension": {
    "schema": "elmos.edge-iot-industrial-evidence.v1",
    "artifactRef": "..."
  }
}

## Evidence类型

OT_ESTATE
PHYSICAL_ASSET_GRAPH
DEVICE_INVENTORY
PLC_RUNTIME_MAP
SCADA_INVENTORY
OT_NETWORK
INDUSTRIAL_TAG_CONTRACT
OPC_UA_RESULT
MQTT_SPARKPLUG_RESULT
PROTOCOL_GATEWAY_RESULT
EDGE_RUNTIME_RESULT
DEVICE_IDENTITY_RESULT
OTA_RESULT
DIGITAL_TWIN_RESULT
TIME_SERIES_QUALITY
EDGE_AI_RESULT
CLOUD_EDGE_SYNC_RESULT
OT_SECURITY_RESULT
SIL_RESULT
HIL_RESULT
SHADOW_RESULT
INDUSTRIAL_CUTOVER
INDUSTRIAL_DECOMMISSION

## Risk映射

PLC_PROJECT_RUNTIME_MISMATCH
→ CONTROL_CONFIGURATION_RISK

UNKNOWN_TAG_SEMANTIC
→ INDUSTRIAL_DATA_RISK

SHARED_DEVICE_CREDENTIAL
→ DEVICE_IDENTITY_RISK

OTA_ROLLBACK_FAILURE
→ FLEET_AVAILABILITY_RISK

TWIN_DIVERGENCE
→ PHYSICAL_DIGITAL_CONSISTENCY_RISK

EDGE_AI_UNSAFE
→ PHYSICAL_PROCESS_RISK

COMMAND_ACK_UNKNOWN
→ CONTROL_ACTION_RISK

## Checks

ELMOS / OT Estate
ELMOS / PLC Runtime
ELMOS / Industrial Semantics
ELMOS / OPC UA
ELMOS / MQTT Sparkplug
ELMOS / Device Identity
ELMOS / OTA
ELMOS / Digital Twin
ELMOS / Time Series
ELMOS / Edge AI
ELMOS / OT Security
ELMOS / Nonstop Validation
ELMOS / Site Cutover

## Composite Change Set

Industrial Modernization Change Set
├── PLC / SCADA Configuration
├── Protocol Gateway
├── Edge Application
├── Device Identity
├── OTA Release
├── Digital Twin
├── Historian Mapping
├── Edge AI Model
├── Network Policy
└── Site Cutover Plan

## Audit

必须审计：

- PLC Project读取；
- Tag Mapping变化；
- 设备注册；
- Certificate；
- OTA；
- Device Command；
- Desired State；
- Edge Model发布；
- Safety例外；
- Shadow转Advisory；
- Command Authority切换；
- 设备退役。

## 验收标准

- 工业Evidence关联设备和应用；
- Safety Gate高于普通功能Gate；
- Command与Telemetry分开；
- 现场Evidence可离线上传；
- Audit和Billing统一；
- Evidence Pack可离线验收。
