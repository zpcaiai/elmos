---
name: github-branch-commit-pr-checks-and-delivery-idempotency
description: "将验证后的Patch安全地提交为主题化Commit、PR和GitHub Checks，并处理超时与重试。"
---

# Delivery Preconditions

Plan Approved
Verification PASS／Approved Warning
Evidence Completeness PASS
Repository Access Active
Delivery Approval Valid
Patch Hash匹配
Snapshot未Stale

## Branch

命名：

elmos/{project-id}/{snapshot-short-sha}

创建前检查：

- Branch是否存在；
- 是否由同一Project创建；
- Snapshot是否一致；
- 是否存在未知Commit。

未知同名Branch：

→ BRANCH_CONFLICT
→ 不覆盖

## Commit

建议：

1. build-and-jdk
2. spring-boot-3-and-jakarta
3. security-and-persistence
4. spring-boot-4
5. bounded-agent-fixes

每个Commit记录：

Patch Segment
Recipe IDs
Verification Ref
Agent Run候选

## Token

Delivery Token只允许：

Contents Write
Pull Requests Write

Checks Token允许：

Checks Write

任务完成后立即丢弃。

## PR Idempotency

Identity：

Repository
Head Branch
Base Branch
Project ID
Snapshot ID

PR创建超时后：

先查询现有PR
再决定重试

不得直接重复创建。

## Check Runs

ELMOS / Baseline
ELMOS / Health Check
ELMOS / OpenRewrite
ELMOS / Compile
ELMOS / Unit Tests
ELMOS / API Compatibility
ELMOS / Agent Repair
ELMOS / Risk
ELMOS / Evidence

状态：

queued
in_progress
completed

结论：

success
neutral
action_required
failure
cancelled
timed_out

## Annotations

将Finding映射到：

Path
Line
Level
Message
Evidence Link

大量Finding需分页或摘要，避免超限。

## PR Body

Target
Source Snapshot
Migration Plan
Recipe Manifest
Build Status
Test Status
API Differences
Known Risks
Manual Tasks
Rollback Notes
Evidence Link

## 禁止

Auto Merge
Force Push Existing Customer Branch
Suppress Failed Check
Delete Customer Commit
Agent Direct Push

## 验收标准

- 只有验证后的Patch可交付；
- Branch冲突不覆盖；
- PR创建重试幂等；
- Checks由GitHub App发布；
- Check可从GitHub UI重新请求；
- Merge由客户完成；
- Token不进入Git历史；
- PR可追踪到Snapshot和Evidence。
