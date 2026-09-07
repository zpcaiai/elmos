---
name: legacy-industrial-protocol-gateway-and-adapter-modernizer
description: 将Modbus、PROFINET、EtherNet/IP、DNP3、BACnet、IEC协议和专有协议封装为受治理Gateway。
---

# Protocol Gateway

## Source Protocol

MODBUS_TCP
MODBUS_RTU
PROFINET
ETHERNET_IP
CAN
CANOPEN
BACNET
DNP3
IEC_104
IEC_61850
S7
ADS
SERIAL_CUSTOM
VENDOR_CUSTOM

## Gateway职责

Connect
Poll
Subscribe
Decode
Scale
Quality
Timestamp
Buffer
Map
Publish
Command
Audit

## Gateway禁止承载

- 核心生产排程；
- 隐藏安全联锁；
- 无Owner业务规则；
- 不可测试的复杂流程；
- 无版本Mapping。

## Polling

记录：

Interval
Timeout
Retry
Batch Read
Address Range
Device Load
Bus Utilization
Priority

## Command

协议写入必须：

- Allowlist地址；
- Data Type；
- Range；
- Sequence；
- Interlock；
- Identity；
- Rate；
- Ack；
- Timeout；
- Compensation。

## Serial

管理：

Port
Baud
Parity
Stop Bit
Address
Collision
Timeout
Exclusive Access

## Protocol Simulation

每个Adapter必须具备：

- Normal；
- Timeout；
- Invalid Frame；
- CRC Error；
- Device Offline；
- Slow Response；
- Wrong Type；
- Out-of-range。

## 验收标准

- Gateway只是边界适配；
- Polling不会压垮设备；
- Mapping版本化；
- 写地址Allowlist；
- Ack语义明确；
- 专有协议可以保留Vendor Extension；
- Gateway故障不破坏本地控制。
