---
name: opc-ua-server-client-pubsub-and-information-model-modernizer
description: 现代化OPC DA和专有接口为OPC UA Client／Server、PubSub、信息模型和证书体系。
---

# OPC UA Modernization

## Inventory

Application
Server
Client
Endpoint
Namespace
Node
Object Type
Variable Type
Method
Event
Reference
Subscription
History
Security Policy
Certificate
Trust List

## 目标路径

KEEP_OPC_UA
UPGRADE_OPC_UA
OPC_DA_TO_UA_GATEWAY
NATIVE_OPC_UA_SERVER
UA_CLIENT_FACADE
UA_PUBSUB
COMPANION_MODEL
RETIRE

## 信息模型

不能只发布平铺Tag。

应建立：

Object Type
Asset
Component
Variable
Method
Event
Relationship
Engineering Unit
Range
Alarm

## Client / Server

适合：

- 浏览；
- 读取；
- 写入；
- Method；
- Subscription；
- History；
- Session身份。

## PubSub

适合：

- 多订阅者；
- 高效Telemetry；
- Broker或Broker-less；
- DataSet结构；
- 边缘分发。

OPC UA PubSub支持Broker与Broker-less环境，消息完整性和保密性由OPC UA消息安全定义。

## Certificate

管理：

Application Identity
Certificate
Trust List
CA
CRL
Expiry
Rotation
Revocation

OPC UA GDS可提供应用发现以及CertificateManager、TrustList、CA和CRL的推送或拉取管理，可作为大规模OPC UA证书Provider。

## 写入

Method和Write需要：

Identity
Role
Asset
Tag
Range
Interlock
Approval
Audit
Acknowledgement

## 验收标准

- OPC UA不只发布平铺Tag；
- Namespace和NodeId稳定；
- Client／Server与PubSub按场景选择；
- Certificate自动生命周期；
- Anonymous生产写默认禁止；
- Write和Method有业务Ack；
- 旧OPC DA Gateway有退出策略。
