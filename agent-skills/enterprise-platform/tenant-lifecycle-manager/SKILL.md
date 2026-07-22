---
name: tenant-lifecycle-manager
description: Govern tenant provisioning, activation, suspension, read-only export, termination, Legal Hold, destruction, and deletion certificates. Use for tenant lifecycle transitions or offboarding.
---

# Tenant Lifecycle Manager

Read `../references/batch-12-enterprise-platform.md`. Enforce the requested-to-destroyed state machine, revoke sessions/Runners before termination, preserve audit, export customer data, evaluate Legal Hold, delete all declared stores and crypto-shred only an independent tenant key.

Transitions must be idempotent and externally executed. Never reuse a destroyed tenant ID or claim deletion before backup/Runner cache closure and a signed deletion certificate.
