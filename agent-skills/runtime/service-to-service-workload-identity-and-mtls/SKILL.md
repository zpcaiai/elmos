---
name: service-to-service-workload-identity-and-mtls
description: "为Control API、Worker、Agent Gateway、Runner和内部服务建立独立工作负载身份和mTLS。"
---

# Workload Identity

Control API
Temporal Worker
Agent Gateway
Runner Gateway
Report Worker
Graph Projector
Private Runner
Sandbox候选

## Identity字段

Service Name
Tenant候选
Environment
Trust Domain
Instance
Certificate
Public Key
Issued At
Expires At
Attestation

## 认证

mTLS
Short-lived JWT
Signed Workload Assertion

禁止共享：

Internal API Key
Cluster-wide Password
Long-lived Static Token

## 授权

服务身份只能调用批准API：

Temporal Worker
→ 创建Runner Task

Runner
→ Poll Lease、上传结果

Agent Gateway
→ 创建受限Agent Task

Graph Projector
→ 读取Outbox，不写业务表

## Rotation

证书自动轮换；
支持新旧证书短暂重叠；
撤销立即停止新连接。

## 验收标准

- 每个服务使用独立身份；
- Runner不能冒充Control API；
- Graph Projector无业务写权限；
- 证书轮换不需要服务停机；
- 撤销服务身份立即生效；
- mTLS Subject进入Audit；
- Trust Domain跨环境隔离。
