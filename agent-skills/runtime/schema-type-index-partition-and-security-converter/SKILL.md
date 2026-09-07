---
name: schema-type-index-partition-and-security-converter
description: Convert database schemas, types, constraints, indexes, partitions, sequences, identities, views, roles, grants, row security, and masking with explicit compatibility and loss findings. Use when generating and validating target DDL for same-engine or heterogeneous database migrations.
---

# Schema Conversion

## Convert explicitly

- Convert tables, columns, defaults, generated expressions, keys, checks, indexes, partitions, sequences, identities, views, materialized views, roles, grants, row security, masking, encryption, and audit settings.
- Give every type mapping a status: LOSSLESS, LOSSLESS_WITH_CONSTRAINT, SEMANTICALLY_COMPATIBLE, LOSSY_APPROVED, REQUIRES_APPLICATION_CHANGE, or UNSUPPORTED.
- Profile precision, scale, range, rounding, unsigned values, character length/encoding/collation, timezone/DST, LOB behavior, JSON/XML semantics, and spatial behavior.
- Require named approval and evidence for every lossy mapping.

## Rebuild physical and security intent

- Derive target indexes from source intent, target engine, and representative workload; do not mechanically copy clustered, bitmap, filtered, included-column, function, spatial, or local/global behavior.
- Redesign partitions for pruning, retention, skew, growth, and maintenance.
- Map owners, roles, grants, row policies, masking, encryption, and service accounts without copying shared DBA accounts, internal roles, or broad PUBLIC grants.

## Validate

- Generate target schema, index, security, manual-decision, and unsupported-object artifacts.
- Test fresh creation, defined repeat execution, schema and security diff, sample data, constraints, indexes, partitions, and rollback.
- Block on unsupported objects, unresolved collation/timezone, unapproved loss, or security regression.
