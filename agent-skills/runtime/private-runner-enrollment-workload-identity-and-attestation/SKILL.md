---
name: private-runner-enrollment-workload-identity-and-attestation
description: "使用一次性Enrollment Token注册Runner，并签发每Runner独立的短期工作负载身份。"
---

# Enrollment

## Enrollment Token

包含：

Token ID
Tenant
Site
Allowed Runner Name
Allowed Capabilities
Maximum Uses = 1
Expiry
Issuer
Approval
Nonce

数据库只保存：

Token Hash
Status
Expiry
Use Count

## 注册流程

Create Enrollment
→ Admin Approves
→ Runner生成Key Pair
→ Runner提交CSR和Attestation
→ Server验证Enrollment
→ Server签发Runner Identity
→ Enrollment Token失效

## Runner Identity

候选：

mTLS Client Certificate
SPIFFE SVID
Short-lived JWT

MVP优先：

mTLS Certificate
+ 自动轮换

## Identity绑定

Runner ID
Tenant
Site
Certificate Public Key
Binary Version
Binary Digest
Approved Capabilities
Network Profile
Maximum Concurrency
Issued At
Expires At

## Attestation

基础版：

Runner Version
Binary Digest
OS
Architecture
Container Runtime
Sandbox Provider
Site
Admin Approval

高保障候选：

TPM
Cloud Instance Identity
SPIRE Node Attestation

## Rotation

证书到期前自动轮换。

旧证书进入：

ROTATING
REVOKED
EXPIRED

## Revocation

撤销后：

- Heartbeat被拒绝；
- 新Lease不签发；
- 活动Task进入Pause／Reconcile；
- Credential加入Revocation List；
- Audit记录原因。

## 状态

PENDING
APPROVED
ENROLLING
ACTIVE
ROTATING
DRAINING
QUARANTINED
REVOKED
EXPIRED

## 验收标准

- Enrollment Token只能使用一次；
- 不同Runner不共享长期Token；
- Runner证书可独立撤销；
- Runner身份绑定Tenant和Site；
- Capabilities不能由Runner自行扩大；
- 轮换无需人工替换Secret；
- 被撤销Runner不能继续领取任务。
