---
name: github-app-installation-repository-sync-and-token-broker
description: "管理GitHub App安装、Repository同步、Webhook、短期Token和Git操作授权。"
---

# GitHub App Integration

## 对象

GitHub App
Installation
Installation Account
Installation Repository
Repository Authorization
Webhook Delivery
Token Lease

## 事件

installation.created
installation.deleted
installation.suspend
installation.unsuspend
installation_repositories.added
installation_repositories.removed
repository.renamed
repository.deleted
push

## Token类型

SNAPSHOT_CLONE
DELIVERY_PUSH
PULL_REQUEST_CREATE
CHECKS_PUBLISH

每类Token独立签发并收窄Permission。

## Token规则

- 即时签发；
- 不持久化；
- 不记录正文；
- 当作Opaque String；
- 只在内存中存在；
- 任务结束立即清除；
- Repository移除后禁止新签发。

## Webhook

Verify Signature
→ Deduplicate Delivery ID
→ Persist Raw Metadata
→ Normalize
→ Publish Outbox
→ Async Process

## Repository Authorization

Installation
Tenant
Repository ID
Repository Node ID
Owner
Permissions
Active State
Last Synced

## 状态

ACTIVE
SUSPENDED
REPOSITORY_REMOVED
INSTALLATION_DELETED
PERMISSION_INSUFFICIENT
SYNC_FAILED

## 验收标准

- 不使用长期PAT；
- Repository移除后Clone和Push立即失败；
- Token权限不超过任务要求；
- Token到期后可重新签发；
- Token格式变化不影响实现；
- Webhook重放不重复创建项目；
- Clone Token和Delivery Token不能互换。
