---
name: github-app-repository-and-webhook-integration
description: "实现GitHub App安装、Repository发现、Webhook、短期Token、PR和Checks。"
---

# Operations

Install App
List Repositories
Import Repository
Clone Lease
Create Branch
Push Commit
Open Pull Request
Publish Check Run
Read Workflow Result

## Security

- 不保存Installation Token；
- Token即时签发；
- Token限制Repository；
- Token限制Permission；
- Webhook签名验证；
- Delivery ID去重；
- GitHub API Version固定。

## 验收标准

- App安装后Repository可见；
- 移除Repository立即停止访问；
- Token过期可重新签发；
- Webhook重放不重复执行；
- PR动作归因GitHub App；
- 无长期PAT。
