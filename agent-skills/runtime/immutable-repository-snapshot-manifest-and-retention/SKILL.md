---
name: immutable-repository-snapshot-manifest-and-retention
description: "固定Repository Commit、Submodule和LFS状态，生成不可变Snapshot及Manifest。"
---

# Repository Snapshot

## 输入

Repository Authorization
Repository ID
Commit SHA
Branch Metadata
Source Policy
Runner ID

## Snapshot Manifest

Repository ID
Provider Repository ID
Commit SHA
Git Tree ID
Default Branch
Submodule Commit Map
LFS Object IDs
Tracked File Count
Build File Digests
Runner ID
Tool Versions
Created At
Manifest Hash

## Source Policy

LOCAL_ONLY
ENCRYPTED_UPLOAD
FULL_PRIVATE_DEPLOYMENT

## 创建流程

Issue Clone Token
→ Clone Exact Commit
→ Verify Commit
→ Resolve Approved Submodules
→ Resolve Approved LFS
→ Generate Manifest
→ Hash Manifest
→ Seal Snapshot

## 不可变性

Snapshot不得原地：

- 更新Branch；
- 替换Commit；
- 修改Submodule；
- 应用Patch；
- 重新计算并覆盖Manifest。

修改必须创建新Snapshot或Worktree。

## Retention

ACTIVE_PROJECT
DELIVERY_WINDOW
AUDIT_RETENTION
DELETE_SOURCE_KEEP_EVIDENCE
LEGAL_HOLD

## 验收标准

- Force Push不改变已有Snapshot；
- 相同Commit和配置可识别为相同内容候选；
- Git Token不进入Manifest；
- Submodule和LFS状态明确；
- Snapshot与修改Worktree分开；
- Source删除后Evidence仍可验证；
- Manifest Hash变化可检测。
