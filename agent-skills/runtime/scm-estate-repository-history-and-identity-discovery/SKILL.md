---
name: scm-estate-repository-history-and-identity-discovery
description: 清点Git与遗留SCM、Repository、Branch、Tag、历史、作者、权限、Hook和实际使用。
---

# SCM Estate Discovery

## SCM类型

GIT
SUBVERSION
TFVC
PERFORCE
CLEARCASE
RTC
CVS
MAINFRAME_SCM
CUSTOM

## Repository对象

- Project；
- Repository；
- Module；
- Branch；
- Tag；
- Changeset；
- Commit；
- Author；
- Binary；
- Large File；
- Submodule；
- External；
- Hook；
- Permission；
- Protection；
- Archive。

## 使用状态

ACTIVE
SEASONAL
DORMANT
ARCHIVED
MIRROR
UNKNOWN

## Owner

记录：

- Business Owner；
- Technical Owner；
- Maintainer；
- Security Owner；
- Archive Owner。

## History

捕获：

Commit Count
Changeset Count
First Change
Last Change
Branch Count
Tag Count
Merge Count
File Count
Repository Size
Binary Size

## Identity

建立：

Legacy Username
Email
Directory Identity
Git Identity
Employment Status

## Author状态

RESOLVED
MULTIPLE_MATCHES
FORMER_EMPLOYEE
SERVICE_ACCOUNT
UNKNOWN

## Hook和自动化

- Commit Hook；
- Server Hook；
- Build Trigger；
- Ticket Integration；
- Promotion；
- Security；
- Mirror；
- Notification。

## Findings

UNKNOWN_REPOSITORY_OWNER
UNKNOWN_COMMIT_AUTHOR
SHARED_COMMIT_IDENTITY
UNPROTECTED_DEFAULT_BRANCH
UNSIGNED_CRITICAL_RELEASE
BINARY_REPOSITORY
LARGE_HISTORY
HIDDEN_BUILD_TRIGGER
PRODUCTION_DEPLOY_FROM_WORKSTATION
SCM_USAGE_UNKNOWN

## 输出

scm-estate.json
repository-inventory.json
repository-history-profile.json
repository-identity-map.json
repository-permission-map.json
repository-automation-map.json
scm-unknowns.json

## 验收标准

- SCM和Repository分开；
- 活跃与归档分开；
- Author Identity有映射状态；
- Hook和隐式Build可见；
- Binary和Large File单独评估；
- Unknown Owner阻止迁移Cutover。
