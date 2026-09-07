---
name: deployment-production-hardening-and-twelve-month-roadmap
description: "实现本地、SaaS、私有和离线部署，并管理12个月工程交付计划。"
---

# Environments

LOCAL
DEV
STAGING
SAAS_PRODUCTION
PRIVATE_PILOT
AIR_GAPPED

## Production Requirements

Managed PostgreSQL候选
Temporal Cloud或受控自托管
Object Store
KMS
OIDC
OTel
Backup
Restore
Rate Limit
Quota
Audit
DR

## Release

Canary
Database Compatibility
Worker Versioning
Rollback
Feature Flag
Migration Gate

## 验收标准

- Compose可本地运行；
- SaaS可多租户；
- 私有版使用同一Artifact；
- Helm安装可验证；
- Backup可恢复；
- Runner离线可清理；
- 12个月Gate可度量。
