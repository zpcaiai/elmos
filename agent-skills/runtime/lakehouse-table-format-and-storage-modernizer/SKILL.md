---
name: lakehouse-table-format-and-storage-modernizer
description: Modernize Hive tables, Parquet directories, analytical copies, and warehouse exports into governed Iceberg, Delta, or hardened Parquet designs. Use for table-format, catalog, compute, partition, protocol, snapshot, compaction, retention, and deletion planning.
---

# Lakehouse Modernization

## Separate platform concerns

- Model storage format, table format, catalog, compute engine, transformation tool, query engine, and governance independently.
- Compare Apache Iceberg, Delta Lake, hardened Parquet, and customer-approved formats without assuming a vendor.
- Keep analytical tables separate from the authoritative OLTP store.

## Prove compatibility

- Record every reader and writer engine, connector, version, read/write capability, table feature, and protocol support.
- Do not enable an unratified table-spec version by default.
- Require approval for protocol or table-feature upgrades that can strand older readers or writers.
- Block on unsupported consumers even if the newest writer succeeds.

## Design operations

- Design field identity, partition evolution, sorting, CDC keys, snapshots, retention, compaction, target file size, orphan cleanup, and catalog ownership from real workload.
- Avoid copying path-style time partitions mechanically.
- Align time travel, legal hold, snapshot expiry, vacuum, deletion, encryption, region, row/column policy, and masking.
- Emit target, compatibility, table design, migration, snapshot, and compaction artifacts.
