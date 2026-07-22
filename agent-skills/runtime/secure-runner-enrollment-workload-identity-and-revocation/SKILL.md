---
name: secure-runner-enrollment-workload-identity-and-revocation
description: "使用一次性Enrollment注册Private Runner，并签发独立、可轮换和可撤销的Runner身份。"
---

# Runner Enrollment

## Enrollment Token

Tenant
Site
Expected Runner Name
Allowed Capabilities
Expiry
Maximum Uses = 1
Created By
Approval

## Enrollment流程

Create One-time Token
→ Runner Generates Key Pair
→ Runner Sends Enrollment Request
→ Verify Token
→ Validate Runner Metadata
→ Optional Admin Approval
→ Issue Runner Identity
→ Mark Token Consumed

## Runner Identity

Runner ID
Tenant
Site
Public Key
Certificate／JWT Subject
Binary Version
Binary Digest
Approved Capabilities
Network Profile
Expiry

## 身份生命周期

PENDING
ACTIVE
ROTATING
SUSPENDED
REVOKED
EXPIRED
QUARANTINED

## 规则

- Enrollment Token不得成为长期Credential；
- Runner之间不能共享Credential；
- Runner Capability只能由服务器批准；
- Runner更新版本或Digest可触发重新审批；
- Revocation必须阻止Heartbeat、Lease和Artifact上传；
- 证书私钥只存在Runner本地。

## 验收标准

- Enrollment Token重放失败；
- 一个Runner泄露不能冒充其他Runner；
- Runner证书可轮换；
- Runner撤销立即停止新Lease；
- Runner重新注册不能自行扩大Capability；
- Runner身份绑定Tenant和Site；
- 服务端不保存Runner私钥。
