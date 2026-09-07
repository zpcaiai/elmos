---
name: openrewrite-recipe-license-execution-and-idempotency
description: "管理OpenRewrite Recipe目录、许可证、前置条件、Dry Run、Apply、Diff、来源和幂等验证。"
---

# OpenRewrite Execution

## Recipe Catalog

Recipe ID
Recipe Version
Artifact Coordinates
Artifact Digest
License
Source
Purpose
Parameters
Preconditions
Supported Source
Supported Target
Risk
Test Profile

## 执行流程

Validate Recipe
→ License Check
→ Preconditions
→ Dry Run
→ Review Diff Metrics
→ Apply to Isolated Worktree
→ First Diff Hash
→ Re-run Same Recipe
→ Second Diff Check
→ Build Candidate

## 状态

NOT_APPLICABLE
DRY_RUN_COMPLETE
APPLIED
NO_CHANGE
FAILED
PARTIAL
LICENSE_BLOCKED
UNSAFE_DIFF
NON_IDEMPOTENT

## Unsafe Diff

修改超出批准：

Module
Path
File Type
Maximum Files
Maximum Lines
Generated Sources
Secrets
Binary
Target Version

时阻止继续。

## Provenance

保存：

OpenRewrite Version
Recipe Artifact
Recipe Version
Recipe Parameters
Recipe Source
License
Input Snapshot
First Diff
Second Diff
Runner Image

## 规则

- Recipe执行于独立Worktree；
- 原Snapshot只读；
- 第二次运行必须无新增Diff；
- License不明确时不得商业执行；
- Recipe失败不能留下半修改的正式Worktree；
- 所有修改可追溯到Recipe。

## 验收标准

- Catalog版本固定；
- License Gate有效；
- Dry Run与Apply可比较；
- 第二次执行无新增Diff；
- 修改范围符合Plan；
- Patch按Step和Wave分段；
- 非幂等Recipe阻止自动Delivery。
