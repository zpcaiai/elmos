---
name: edge-iot-industrial-engine-contract-and-site-runner
description: 实现边缘、IoT和工业现代化引擎、现场Runner、协议Adapter和ELMOS统一任务契约。
---

# Industrial Engine

## Capability

{
  "engine": "ELMOS_EDGE_IOT_INDUSTRIAL",
  "engineVersion": "1.0.0",
  "capabilities": [
    "OT_DISCOVERY",
    "PLC_SCADA_ANALYSIS",
    "INDUSTRIAL_PROTOCOL",
    "OPC_UA",
    "MQTT_SPARKPLUG",
    "EDGE_RUNTIME",
    "DEVICE_IDENTITY",
    "OTA",
    "DIGITAL_TWIN",
    "TIME_SERIES",
    "EDGE_AI",
    "CLOUD_EDGE_SYNC",
    "OT_SECURITY",
    "NONSTOP_CUTOVER"
  ]
}

## API

GET  /engine/v1/capabilities
POST /engine/v1/discover
POST /engine/v1/plan
POST /engine/v1/execute-step
POST /engine/v1/validate
POST /engine/v1/command
GET  /engine/v1/jobs/{jobId}
POST /engine/v1/jobs/{jobId}/cancel

## Site Runner职责

- 在现场网络执行只读发现；
- 连接批准的协议Endpoint；
- 缓存任务和Policy；
- 执行离线验证；
- 采集Evidence；
- 受控执行OTA；
- 发送经过批准的设备Command；
- 断网期间保持安全状态。

## 默认禁止

- 任意写PLC；
- 修改Safety PLC；
- 下载PLC程序；
- 清除SCADA Alarm；
- 绕过现场联锁；
- 自动下发全厂OTA；
- 直接开放现场设备到公网；
- 把控制权依赖云连接。

## Runner连接

默认：

OUTBOUND_ONLY
MUTUAL_TLS
SHORT_LIVED_LEASE
SITE_ALLOWLIST
LOCAL_POLICY_ENFORCEMENT

## Command等级

READ
ADVISORY
REVERSIBLE_WRITE
CONTROL_WRITE
SAFETY_RELATED
PROHIBITED

## 验收标准

- 控制面与现场隔离；
- Runner断网可继续安全运行；
- 所有写操作分级；
- Safety操作默认禁止；
- Local Policy高于云端请求；
- Evidence可在恢复联网后上传。
