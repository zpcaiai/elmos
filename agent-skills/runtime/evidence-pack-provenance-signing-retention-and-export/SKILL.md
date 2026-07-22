---
name: evidence-pack-provenance-signing-retention-and-export
description: "汇总Snapshot、Plan、Recipe、Patch、验证、审批和PR元数据并生成不可篡改Evidence Pack。"
---

# Evidence Pack

## 内容

Repository Authorization Summary
Snapshot Manifest
Baseline Environment
Baseline Build
Health Report
Target Profile
Migration Plan
Plan Approval
Recipe Manifest
Recipe License
Rewrite Diffs
Idempotency Result
Target Build
Test Results
API Compatibility
Risk Register
Manual Tasks
Delivery Approval
PR Metadata
Check Results
Artifact Digests
Audit Summary

## Manifest

Evidence Pack ID
Tenant
Project
Snapshot
Plan
Created At
Artifacts
Artifact Hashes
Policy Version
Signer
Manifest Hash

## Source Policy

默认不包含：

完整源码
完整Secret
Provider Token
不必要Prompt
客户敏感配置正文

Patch和必要Evidence按Policy处理。

## Integrity

Artifact Hash
Manifest Hash
Digital Signature候选
Immutable Object Lock候选
Audit Anchor候选

## 状态

DRAFT
COMPLETE
SEALED
EXPORTED
SUPERSEDED
RETENTION_HOLD
DELETED_SOURCE_METADATA_RETAINED

## Retention

Source Workspace
Patch
Build Logs
Test Results
Audit
Evidence Pack

分别设置保留期。

## 验收标准

- 所有核心Gate均有Evidence；
- Manifest可离线验证；
- 修改Artifact后Hash失败；
- Evidence关联Snapshot和Plan；
- Secret不会进入Pack；
- 删除源码不删除必须保留的交付证据；
- 历史Pack不能原地覆盖；
- Export结果可重复校验。
