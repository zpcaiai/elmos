---
name: deployment-release-promotion-and-gitops-modernizer
description: 标准化部署、Release、Artifact Promotion、GitOps、渐进发布、验证和回滚。
---

# Release Modernization

## Release对象

Artifact
Configuration
Database Change
Feature Flag
Infrastructure
Client Version
Suite Package
Mainframe Package

## Release与Deployment

Release：
使能力对用户可用。

Deployment：
将Artifact放入运行环境。

两者可以分开。

## Deployment模式

PIPELINE_PUSH
GITOPS_PULL
PLATFORM_API
MANUAL_CONTROLLED
VENDOR_PLATFORM
APP_STORE

## GitOps分类

FULL_GITOPS
GITOPS_COMPATIBLE
DECLARATIVE_PUSH
NON_DECLARATIVE
UNSUPPORTED

## Desired State

必须绑定：

- Repository；
- Commit；
- Artifact Digest；
- Environment；
- Config；
- Secret Reference；
- Policy。

## Promotion

DEV
TEST
UAT
PREPROD
PRODUCTION
DR

## Progressive Delivery

INTERNAL
CANARY
PERCENTAGE
TENANT
REGION
BLUE_GREEN
FEATURE_FLAG
FULL

## Verification

- Health；
- SLO；
- Contract；
- Business Metric；
- Data；
- Error；
- Security；
- Cost。

## Rollback

TRAFFIC
ARTIFACT
CONFIG
FEATURE
DATABASE_FORWARD_FIX
ENVIRONMENT
FULL_RELEASE

## GitOps Drift

DETECTED
RECONCILING
RECONCILED
BLOCKED
MANUAL_OVERRIDE
UNKNOWN

## 验收标准

- Release和Deployment分开；
- Desired State版本化；
- Artifact绑定Digest；
- GitOps符合四项原则；
- 渐进发布有Gate；
- 数据库变化有独立恢复策略。
