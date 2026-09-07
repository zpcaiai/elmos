---
name: immutable-repository-snapshot-submodule-lfs-and-retention
description: "创建指定Commit的不可变Repository Snapshot，处理Submodule、LFS、Force Push和源码保留策略。"
---

# Snapshot Workflow

Authorize Repository
→ Issue Clone Token
→ Fetch Exact Commit
→ Verify Commit Object
→ Checkout Detached Worktree
→ Resolve Submodules
→ Resolve LFS Objects
→ Generate Manifest
→ Verify Manifest
→ Seal Snapshot

## Git Credential

使用：

GIT_ASKPASS
或
进程内Credential Helper

禁止把Token写进：

Remote URL
.git/config
Shell History
Log
Manifest

## Snapshot Identity

Repository Global ID
GitHub Repository ID
Commit SHA
Git Tree SHA
Submodule Map
LFS OID Map
Source Policy
Manifest Hash

## Manifest

{
  "repositoryId": "...",
  "commitSha": "...",
  "treeSha": "...",
  "submodules": [],
  "lfsObjects": [],
  "buildFiles": [],
  "sourcePolicy": "LOCAL_ONLY",
  "manifestHash": "..."
}

## Source Policy

LOCAL_ONLY

源码留在Private Runner；
Control Plane仅保存Manifest和Evidence。

ENCRYPTED_UPLOAD

上传加密Snapshot Artifact。

PRIVATE_CONTROL_PLANE

所有服务部署在客户环境。

## Force Push

旧Commit即使从Branch不可见：

已有Snapshot仍保持有效。

新执行必须创建新Snapshot。

## Submodule

每个Submodule必须：

- 单独授权；
- 固定Commit；
- 独立Token；
- 记录来源；
- 缺少授权时明确失败。

## LFS

记录：

LFS Pointer
Object OID
Size
Download Result
Policy

## Retention

Snapshot Lease
Workspace TTL
Artifact Retention
Legal Hold
Customer Delete Request

## 验收标准

- 相同Repository＋Commit产生同一内容Hash；
- Snapshot不可原地更新；
- Force Push不修改已有Snapshot；
- Submodule权限逐个验证；
- LFS缺失明确报告；
- LOCAL_ONLY模式不上传源码；
- Workspace到期后可靠销毁。
