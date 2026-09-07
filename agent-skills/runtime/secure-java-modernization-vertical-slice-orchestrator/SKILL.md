---
name: secure-java-modernization-vertical-slice-orchestrator
description: "编排从OIDC认证、GitHub授权、Private Runner、Snapshot、Maven基线、OpenRewrite到PR和Evidence Pack的完整安全闭环。"
---

# Java Modernization Orchestrator

## 输入

Tenant Context
Repository Authorization
Runner Selection Policy
Source Commit
Target Profile
Recipe Catalog Version
Policy Bundle Version

## 输出

Migration Project
Workflow ID
Snapshot
Health Report
Migration Plan
Verified Patch
Pull Request
Evidence Pack

## Workflow

Authenticate
→ Authorize Tenant
→ Verify Repository Authorization
→ Select Runner
→ Create Snapshot
→ Run Baseline
→ Run Health Check
→ Generate Plan
→ Wait for Approval
→ Execute Rewrite
→ Verify Idempotency
→ Compile and Test
→ Wait for Delivery Approval
→ Publish PR
→ Seal Evidence

## 规则

- Workflow只维护状态和顺序；
- Git、Maven、OpenRewrite和GitHub调用全部进入Activity或Runner；
- 所有Activity带Idempotency Key；
- Workflow版本、Plan版本、Recipe版本和Policy版本固定；
- 用户取消必须传播到Runner Lease和Sandbox；
- UNKNOWN_RESULT进入Reconciliation，不直接Retry。

## Signal

approvePlan
rejectPlan
approveDelivery
rejectDelivery
cancel
provideCredential
resumeAfterManualAction

## Query

currentStage
currentDecision
currentRunner
currentRisk
latestEvidence
waitingReason

## 验收标准

- Worker崩溃后可恢复；
- 人工审批等待不占执行线程；
- 重复启动不会产生多个Workflow；
- Workflow与数据库状态可以对账；
- 取消可以终止未提交任务；
- 每个状态都能追溯到Evidence。
