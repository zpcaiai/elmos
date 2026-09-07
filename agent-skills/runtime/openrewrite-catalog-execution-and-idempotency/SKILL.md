---
name: openrewrite-catalog-execution-and-idempotency
description: "管理Recipe版本、许可证、适用条件、执行、Patch、第二次运行和证据。"
---

# Catalog

Recipe ID
Version
BOM
License
Source
Purpose
Inputs
Preconditions
Risk
Test Profile

## Execution

Dry Run
→ Review Result
→ Apply
→ Build
→ Run Again
→ Verify No New Diff

## Result

APPLIED
NO_CHANGE
FAILED
PARTIAL
NON_IDEMPOTENT
LICENSE_BLOCKED
NOT_APPLICABLE

## Patch Segmentation

Build
JDK
Jakarta
Security
Persistence
Testing
Boot4
Cleanup

## 验收标准

- 使用OpenRewrite BOM；
- Recipe版本固定；
- 许可证可追踪；
- 第二次运行无新Diff；
- Patch按主题分段；
- Recipe失败不破坏原Worktree；
- 每项修改关联Recipe。
