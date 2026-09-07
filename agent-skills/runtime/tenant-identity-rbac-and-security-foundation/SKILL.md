---
name: tenant-identity-rbac-and-security-foundation
description: "实现多租户、OIDC、RBAC、RLS、Secret、审计和企业SSO基础。"
---

# Roles

TENANT_ADMIN
MIGRATION_MANAGER
DEVELOPER
REVIEWER
SECURITY_REVIEWER
BILLING_VIEWER
AUDITOR
READ_ONLY

## Scope

Organization
Repository
Project
Runner
Artifact
Decision
Policy

## Authentication

Local Development：
Keycloak候选

SaaS：
OIDC Provider

Enterprise：
Okta / Entra / Keycloak / Custom OIDC

## Tenant Isolation

PostgreSQL RLS
Object Prefix
Runner Pool
Encryption Key
Agent Policy
Usage Meter

## 验收标准

- 每张业务表包含tenant_id；
- RLS测试覆盖跨租户攻击；
- Secret不出现在日志；
- 高风险操作需要二次授权候选；
- Audit记录Actor、Tenant和Request；
- Enterprise可配置SSO。
