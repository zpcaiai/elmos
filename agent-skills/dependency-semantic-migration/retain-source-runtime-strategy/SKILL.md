---
name: retain-source-runtime-strategy
description: Formalize temporary or durable retention of a source-language runtime with explicit interface, ownership, deployment, risks, and exit criteria. Use when rewriting is less safe than retaining.
---
# Retain Source Runtime Strategy
Read `../references/dependency-migration-v1.md`. Record why retention is necessary, source snapshot/artifact/runtime identity, interface and data boundary, deployment, scaling, security, monitoring, support, cost, rollback, owner, review date and exit/migration criteria. Retention is an explicit architecture decision, not failure. Never copy opaque runtime code without provenance, leave an ownerless permanent bridge, expose unrestricted execution, or mark retained behavior validated without boundary and differential evidence.
