---
name: openrewrite-catalog-license-dryrun-execution-and-idempotency
description: "管理Recipe来源、版本、许可证、适用条件、Dry Run、Apply、Patch分段和幂等性。"
---

# Recipe Catalog

Recipe ID
Recipe Name
Artifact Coordinates
Version
Source Repository
License
Commercial Use Policy
Input Schema
Preconditions
Risk
Supported Source
Supported Target
Verification Profile

## Recipe状态

DRAFT
EVALUATED
APPROVED
ACTIVE
DEPRECATED
LICENSE_BLOCKED
QUARANTINED
RETIRED

## Selection

输入：

Technology Fingerprint
Source Version
Target Profile
Tenant License Policy
Project Constraints

输出：

Selected Recipes
Order
Expected Effect
License Decision
Fallback

## Dry Run

执行：

rewrite:dryRun
failOnInvalidActiveRecipes=true
exportDatatables=true

收集：

Patch
Datatables
Warnings
Changed Files
Recipe Trace
Parser Errors

## Apply

只在独立Worktree中执行：

rewrite:run

原Snapshot保持只读。

## Patch Segmentation

BUILD
JDK
JAKARTA
SECURITY
PERSISTENCE
TESTING
BOOT4
CLEANUP

每个Segment具有独立Hash和验证结果。

## Idempotency

Apply完成后：

1. 保存Git Diff；
2. 再次执行相同Recipe；
3. 再次执行Dry Run；
4. 要求无新的有效Diff。

结果：

IDEMPOTENT
NON_IDEMPOTENT
INCONCLUSIVE

## License

决策：

ALLOW
ALLOW_WITH_NOTICE
REQUIRE_LICENSE
DENY
MANUAL_REVIEW

## 错误代码

RECIPE_NOT_APPLICABLE
RECIPE_CONFIGURATION_INVALID
RECIPE_LICENSE_BLOCKED
RECIPE_PARSER_FAILED
RECIPE_EXECUTION_FAILED
RECIPE_NON_IDEMPOTENT
RECIPE_CHANGED_UNEXPECTED_FILE

## 验收标准

- Recipe版本固定；
- Recipe许可证可追踪；
- Dry Run先于Apply；
- 原Snapshot不被修改；
- 第二次运行无新Diff；
- Patch按主题分段；
- 每个修改可追到Recipe；
- 非幂等Recipe不能自动Delivery。
