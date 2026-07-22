---
name: mqtt-sparkplug-broker-topic-session-and-state-modernizer
description: 治理MQTT Broker、Client、Topic、Session、QoS、Retained State、Sparkplug Namespace和Birth／Death。
---

# Industrial MQTT

## Inventory

Broker
Listener
Client
Client ID
Topic
Subscription
Shared Subscription
QoS
Retained
Session
Will
Authentication
Authorization
Bridge

## Topic Contract

Organization
Site
Line
Asset
Signal
Purpose
Direction
Schema
Owner
Retention
Classification

## QoS

QOS_0
QOS_1
QOS_2

QoS只是MQTT传输保证，不自动等于业务副作用一次执行。

## Session

记录：

Clean Start
Session Expiry
Inflight Message
Subscription
Offline Queue
Will
Reconnect

## Retained

Retained Message用于新订阅者获取Topic最近保留值，但不能无条件作为权威Digital Twin。

## Sparkplug

对象：

Group
Edge Node
Device
Metric
Birth
Death
Sequence
Alias
State

## Birth / Death

验证：

- Edge Node上线；
- Device Metric完整；
- 不正常离线；
- Session重建；
- Alias重置；
- Broker故障；
- 双网关冲突。

## Bridge

跨Broker Bridge需要：

- Loop防护；
- Topic映射；
- Identity；
- QoS；
- Retained；
- Session；
- Duplicate；
- Sequence。

## Findings

SHARED_MQTT_CREDENTIAL
DUPLICATE_CLIENT_ID
TOPIC_NO_OWNER
UNBOUNDED_WILDCARD
RETAINED_COMMAND
SESSION_STATE_UNKNOWN
SPARKPLUG_BIRTH_INCOMPLETE
SPARKPLUG_SEQUENCE_RESET
BROKER_BRIDGE_LOOP

## 验收标准

- Topic有Owner；
- QoS和业务幂等分开；
- Session和Retained分开；
- Command默认不得Retain；
- Sparkplug Birth完整；
- Client ID唯一；
- Broker Bridge可检测Loop。
