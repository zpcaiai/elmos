---
name: github-branch-commit-pr-checks-and-delivery-governor
description: "将验证后的Patch以主题化Commit、Pull Request和GitHub Checks安全交付。"
---

# Delivery

## 前置条件

Verified Patch
Verification Decision PASS／Approved Warning
Delivery Approval
Active GitHub Installation
Repository Authorization
Valid Snapshot
Evidence Draft

## Branch

分支命名：

elmos/{project-id}/{snapshot-short-sha}

不得覆盖未知同名分支。

## Commit

BUILD_AND_JDK
BOOT_AND_JAKARTA
SECURITY_AND_PERSISTENCE
TESTS
FINAL_TARGET
CLEANUP

每个Commit保存：

Plan Step
Patch Hash
Verification Reference

## Token

Branch／Push Token
PR Token
Checks Token

按所需Permission分别签发。

## PR Body

Source
Target
Scope
Major Changes
Build
Tests
API Compatibility
Known Risks
Manual Tasks
Rollback
Evidence Reference

## Checks

ELMOS / Snapshot
ELMOS / Baseline
ELMOS / Health Check
ELMOS / OpenRewrite
ELMOS / Idempotency
ELMOS / Compile
ELMOS / Tests
ELMOS / API Compatibility
ELMOS / Risk
ELMOS / Evidence

## 幂等

Branch
Commit Tree
PR Head
Project ID
Snapshot ID

共同用于识别重复Delivery。

## Unknown Result

GitHub API超时时：

查询Branch
查询Commit
查询Open PR
查询Check External ID

先对账，不直接重复创建。

## 验收标准

- PR只包含验证Patch；
- 不自动Merge；
- Token不进入Git配置持久层；
- 分支冲突不会被覆盖；
- PR创建可幂等恢复；
- Check可重复更新；
- PR关联固定Snapshot和Plan；
- GitHub撤权后Delivery停止。
