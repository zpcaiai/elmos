---
name: cache-contract-migrator
description: "Migrate method, object, HTTP, memory, and distributed cache operations and policies. Use for framework cache annotation, decorator, or provider conversion."
---
# Cache Contract Migrator
Read `../references/afsm-v1.md`. Preserve cache region/backend/key/tenant namespace, TTL/sliding, null handling, serialization, stampede control, error policy, invalidation and transaction ordering.

Lift key expressions before lowering and never cache tracking proxies. Block distributed-to-local changes, tenant key loss, changed TTL/defaults or pre-commit invalidation without verified equivalence and differential tests.

