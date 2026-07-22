---
name: github-pr-checks-report-and-evidence-delivery
description: "创建分支、Commit、PR、GitHub Checks、报告和验收Evidence Pack。"
---

# Delivery

Create Branch
Apply Verified Patch
Create Commits
Push
Open PR
Publish Checks
Attach Report
Seal Evidence

## Checks

ELMOS / Baseline
ELMOS / OpenRewrite
ELMOS / Compile
ELMOS / Unit Tests
ELMOS / API Compatibility
ELMOS / Agent Repair
ELMOS / Risk
ELMOS / Evidence

## PR Body

Target
Scope
Major Changes
Build
Tests
Known Risks
Human Tasks
Rollback
Evidence Link

## Evidence Pack

Snapshot Manifest
Plan
Recipe Manifest
Agent Manifest
Patch
Build Results
Test Results
Compatibility Results
Approvals
PR Metadata
Artifact Digests

## 验收标准

- PR只包含验证后的Patch；
- Commit按迁移主题；
- Check可重试且幂等；
- Evidence Pack有Manifest和Hash；
- PR关闭不删除Evidence；
- Merge由客户完成。
