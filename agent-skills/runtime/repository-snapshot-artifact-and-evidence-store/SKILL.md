---
name: repository-snapshot-artifact-and-evidence-store
description: "创建不可变Repository Snapshot、Manifest、Artifact和Evidence引用。"
---

# Snapshot Identity

Repository ID
Commit SHA
Submodule Map
Git LFS State
Build Metadata
Snapshot Manifest Hash

## Snapshot状态

REQUESTED
CLONING
MATERIALIZED
VERIFIED
READY
FAILED
EXPIRED
DELETED

## Artifact

BUILD_LOG
TEST_REPORT
PATCH
DEPENDENCY_GRAPH
FINGERPRINT
SBOM
REPORT
PR_METADATA
EVIDENCE_PACK

## Source Policy

LOCAL_ONLY
ENCRYPTED_UPLOAD
PRIVATE_DEPLOYMENT

## 验收标准

- 相同Commit生成相同Snapshot ID候选；
- Snapshot不可原地修改；
- Artifact使用Digest；
- 大Artifact不进入PostgreSQL；
- 删除遵循Retention；
- Evidence可追踪到Snapshot。
