---
name: device-identity-pki-zero-trust-and-secure-onboarding
description: 管理设备、Gateway、Edge Node和Workload的唯一身份、证书、注册、授权和退役。
---

# Device Identity

## Identity层级

Manufacturer
Product
Model
Device Instance
Gateway
Edge Node
Workload
Operator
Service

## Onboarding

Manufactured
→ Claimed
→ Verified
→ Enrolled
→ Certificate Issued
→ Policy Assigned
→ Activated

## Evidence

Serial
Hardware ID
Secure Element
TPM
Attestation
Factory Certificate
Installation Code
Operator Approval

## Credential

DEVICE_CERTIFICATE
WORKLOAD_CERTIFICATE
SHORT_LIVED_TOKEN
HARDWARE_KEY
LEGACY_PASSWORD
SHARED_SECRET

目标优先顺序：

Hardware-backed Identity
→ Device Certificate
→ Short-lived Token
→ Unique Password
→ Shared Secret Temporary Only

## Authorization

按：

Device
Site
Topic
OPC Namespace
Twin
Command
OTA Ring
Environment
Time

## Certificate Lifecycle

Issue
Activate
Renew
Rotate
Revoke
Replace
Destroy

## GDS与PKI

OPC UA设备可通过GDS／CertificateManager实现证书和TrustList集中管理，但其他MQTT、HTTP和Edge设备仍需要统一Device PKI抽象。

## Decommission

- Certificate撤销；
- Broker ACL删除；
- Twin归档；
- OTA停止；
- 数据保留；
- 物理资产状态更新。

## 验收标准

- 每台设备拥有唯一身份；
- Shared Secret形成技术债；
- Certificate自动轮换；
- Policy绑定Site和用途；
- 失窃设备可撤销；
- Decommission清理所有访问；
- Onboarding可审计。
