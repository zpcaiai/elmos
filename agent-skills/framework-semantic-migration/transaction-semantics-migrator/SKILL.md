---
name: transaction-semantics-migrator
description: "Migrate transaction boundaries, propagation, isolation, rollback, timeout, resource synchronization, outbox, and async context. Use for framework or ORM transaction conversion."
---
# Transaction Semantics Migrator
Read `../references/afsm-v1.md`. Preserve callable boundary, propagation, isolation, read-only, timeout, rollback/no-rollback rules, proxy/self-invocation behavior, resources and completion events.

Do not reduce `requires-new`, widen or shrink boundaries silently, or assume thread-local context crosses awaits/tasks. Treat caught failures, cancellation and multiple resources explicitly. Require rollback/database-state integration evidence and human review for Agent patches.

