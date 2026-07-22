---
name: github-webhook-idempotency-and-access-reconciliation
description: "安全处理GitHub Webhook，完成签名验证、去重、原始Envelope留证、异步处理和Repository访问对账。"
---

# Webhook Ingress

## 流程

Receive Request
→ Verify HMAC
→ Validate Event Type
→ Deduplicate Delivery ID
→ Persist Envelope Metadata
→ Write Outbox
→ Return 2xx
→ Async Process

## Header

X-GitHub-Event
X-GitHub-Delivery
X-Hub-Signature-256

## 去重

数据库唯一键：

(provider, delivery_id)

重复Webhook：

相同Hash
→ 返回成功，不重复副作用

相同Delivery ID但不同Hash
→ 记录Security Incident

## 事件

installation
installation_repositories
repository
push
pull_request
check_run
check_suite
workflow_run

只订阅实际使用的事件。

## 原始Payload

保存策略：

- 默认保存加密Payload；
- 设置Retention；
- 对Secret和Token字段Redact；
- 保存Payload Hash；
- 解析后生成版本化Normalized Event。

## Reconciliation

定期执行：

Stored Installation Repositories
vs
GitHub Current Installation Repositories

识别：

ACCESS_ADDED
ACCESS_REMOVED
REPOSITORY_RENAMED
REPOSITORY_TRANSFERRED
REPOSITORY_ARCHIVED
INSTALLATION_SUSPENDED

## Outbox事件

GitHubInstallationActivated
GitHubRepositoryGranted
GitHubRepositoryRevoked
GitHubInstallationSuspended
GitHubPushObserved
GitHubCheckRerequested

## 验收标准

- 无效签名请求被拒绝；
- 重放Webhook不重复创建Project；
- API处理不在Webhook请求线程完成；
- Repository移除最终可被定期对账发现；
- Payload冲突触发Security Event；
- 所有Webhook具有Correlation ID；
- Outbox恢复后事件可继续处理。
