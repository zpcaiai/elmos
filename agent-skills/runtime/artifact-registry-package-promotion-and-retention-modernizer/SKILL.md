---
name: artifact-registry-package-promotion-and-retention-modernizer
description: 统一管理软件包、OCI Artifact、签名、元数据、晋级、隔离、保留和退役。
---

# Artifact Registry

## Artifact类型

MAVEN
NUGET
NPM
PYPI
OCI_IMAGE
OCI_ARTIFACT
HELM
IAC_MODULE
MOBILE_PACKAGE
DESKTOP_INSTALLER
DATABASE_MIGRATION
MAINFRAME_PACKAGE
GENERIC

## Artifact Identity

Name
Version
Digest
Platform
Architecture
Build
Source Commit
Builder
Created At

## Repository类型

DEVELOPMENT
SNAPSHOT
RELEASE
QUARANTINE
PROMOTION
ARCHIVE
EXTERNAL_PROXY

## Promotion

Build Artifact
→ Development
→ Test-approved
→ Release
→ Production-approved

Artifact内容不变化。

Promotion只改变：

- 可见范围；
- Policy状态；
- Channel；
- Environment Eligibility。

## Metadata关联

- SBOM；
- Provenance；
- Signature；
- Test；
- Vulnerability；
- License；
- Approval；
- Deployment。

## Mutable Tag

Tag可以变化，但：
