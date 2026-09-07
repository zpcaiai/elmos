---
name: database-estate-workload-and-usage-discovery
description: Discover and inventory database instances, databases, schemas, objects, capacity, workload, consumers, jobs, and cross-database dependencies with bounded evidence. Use for Oracle, SQL Server, MySQL, or PostgreSQL estate assessment, workload capture, usage classification, and migration-scope baselining.
---

# Database Estate Discovery

## Discover in layers

- Record organization, environment, instance, database, schema, object, workload, and consumer as distinct identities.
- Capture engine, edition, version, patch, platform, character set, collation, timezone, HA, backup, replication, encryption, license features, capacity, growth, and log generation.
- Inventory tables, columns, constraints, indexes, partitions, sequences, identities, views, routines, packages, triggers, jobs, links, extensions, roles, users, and grants.
- Bind all observations to a capture window and source such as AWR/ASH, Query Store, Performance Schema, pg_stat_statements, trace, audit, or application log.

## Normalize without losing evidence

- Fingerprint query literals, parameters, whitespace, comments, aliases, and case while retaining dialect, schema, operation, parameter types, plans, and runtime.
- Classify work as read, write, DDL, transaction, batch, report, ETL, admin, or unknown.
- Identify application, BI, ETL, scheduler, stored routine, vendor, human, and unknown consumers.
- Mark objects without observations as DORMANT, never UNUSED, unless the evidence window and authoritative usage sources justify it.
- Add database links, linked servers, FDW, federated tables, synonyms, external tables, files, and ETL edges to the migration dependency graph.

## Emit

- Emit estate, object inventory, capacity, workload, query fingerprint, consumer, and cross-database dependency artifacts.
- Raise explicit findings for unknown writers/consumers, shared-schema coupling, collation or character-set risk, hot tables, high log volume, and incomplete metadata.
- Fail closed when required metadata or workload sources cannot be read.
