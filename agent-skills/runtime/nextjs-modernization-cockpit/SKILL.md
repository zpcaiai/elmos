---
name: nextjs-modernization-cockpit
description: "实现Repository、项目、运行、报告、决策和Runner的Next.js驾驶舱。"
---

# Routes

/dashboard
/repositories
/repositories/{id}
/projects
/projects/{id}
/projects/{id}/runs/{runId}
/reports/{id}
/runners
/integrations
/policies
/audit
/settings

## Project View

Summary
Technology Fingerprint
Risk
Plan
Timeline
Build
Tests
Patch
PR
Evidence

## Live Progress

使用：

Server-sent Events

而不是每秒轮询所有Workflow。

## Security

- OIDC Session；
- Tenant切换显式；
- Server-side Authorization；
- 下载Artifact使用短期URL；
- 敏感日志默认折叠；
- 不在浏览器保存Provider Secret。

## 验收标准

- 用户可从Repository创建项目；
- Timeline显示Temporal步骤；
- 失败可下钻到Evidence；
- 人工Gate可审批或拒绝；
- 页面刷新不丢失状态；
- 无权限用户无法猜ID访问其他Tenant。
