---
name: git-scm-consolidation-migration-and-governance
description: 将遗留SCM安全迁往Git，保留历史、身份、Branch、Tag、权限和审计，并建立Repository治理。
---

# SCM Migration

## 目标策略

KEEP_CURRENT_SCM
UPGRADE_CURRENT_SCM
MIRROR_TO_GIT
MIGRATE_TO_GIT
SPLIT_REPOSITORY
MERGE_REPOSITORIES
ARCHIVE
RETIRE

## 不强制统一Repository模型

候选：

MONOREPO
MULTIREPO
HYBRID
PLATFORM_REPOSITORY
CONFIGURATION_REPOSITORY
DEPENDENCY_REPOSITORY

## Migration步骤

Inventory
→ Identity Map
→ History Conversion
→ Branch and Tag Conversion
→ Binary Strategy
→ Hook Replacement
→ Permission Mapping
→ Dry Run
→ Hash and Count Validation
→ Freeze Window
→ Final Delta
→ Read-only Legacy
→ Cutover

## History

验证：

- Changeset数量；
- Author；
- Time；
- File；
- Branch；
- Tag；
- Merge；
- Delete；
- Rename；
- Binary；
- Encoding。

源和Git Hash本身通常不同。

因此验证：
