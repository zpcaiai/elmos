---
name: offline-license-and-entitlement-manager
description: Verify signed installation-bound offline licenses, entitlements, quotas, validity, grace, clock rollback, emergency access, renewal, and safe expiry. Use for disconnected licensing behavior.
---

# Offline License and Entitlement Manager

Read `../references/batch-12-enterprise-platform.md`. Validate signature, tenant/installation, limits, time and anti-rollback locally; allow safe task completion/read/export/audit and renewal during expiry while denying new migration after policy. Emergency licenses are bounded and audited.

Never delete or corrupt customer data on expiry. Tamperable or online-dependent licensing blocks T-F.
