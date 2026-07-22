---
name: fixture-e2e-security-recovery-and-release-validation
description: "使用真实Fixture Repository和故障场景验证整条MVP链的正确性、安全性和可恢复性。"
---

# Fixture Repository

BOOT27_MAVEN_MONOLITH
BOOT27_MAVEN_MULTIMODULE
JAVA11_PRIVATE_REPOSITORY
BASELINE_BROKEN
JAVAX_HEAVY
SECURITY_LEGACY
HIBERNATE_LEGACY
TEST_DISCOVERY_REGRESSION
BUILD_MUTATES_SOURCE
MALICIOUS_BUILD_SCRIPT

## Security Test

Forged Tenant Header
Cross-tenant UUID
Runtime Superuser Check
Webhook Replay
Enrollment Replay
Revoked Runner
Sandbox Escape
Unknown Network
Secret Read
Cross-tenant Cache
Cross-tenant Artifact

## Recovery Test

Control API Restart
Temporal Worker Restart
Runner Disconnect
Lease Expiry
Sandbox Crash
Object Upload Orphan
GitHub API Timeout
PR Unknown Result
Database Failover候选
Evidence Tampering

## Release Gate

AUTHORIZATION_PASS
RLS_PASS
RUNNER_IDENTITY_PASS
SANDBOX_PASS
SNAPSHOT_PASS
BASELINE_PASS
REWRITE_IDEMPOTENCY_PASS
VERIFICATION_PASS
DELIVERY_IDEMPOTENCY_PASS
EVIDENCE_INTEGRITY_PASS
RECOVERY_PASS

## 最小商业Gate

必须在以下三类Repository重复通过：

Boot 2.7 Maven单体
Boot 2.7 Maven多模块
Java 11企业私服项目

## 验收标准

- 使用真实PostgreSQL执行RLS测试；
- Temporal崩溃恢复通过；
- Runner失联进入Reconciliation；
- 恶意构建无法逃逸；
- GitHub重复操作不创建重复PR；
- Evidence篡改可检测；
- 全链路至少连续成功执行多次；
- Release Gate可自动运行。
