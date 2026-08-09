
# Batch 31 Database Route Matrix

Each route is directional and exact. Examples:

```text
Oracle 19c Enterprise → PostgreSQL 16
SQL Server 2022 → PostgreSQL 16
MySQL 8.0 → PostgreSQL 16
PostgreSQL 14 → PostgreSQL 16
Stored Procedure → Application Service
Legacy ETL → Modern Pipeline
Warehouse → Lakehouse
```

A route tuple includes at least:

```text
engine
version
edition/service tier
compatibility mode
SQL dialect
client/driver versions
charset
collation
session time zone
extensions/plugins
operating mode
```

Capability states:

```text
certified
supported
conditional
experimental
detected-only
blocked
```

Pack states:

```text
research
experimental
limited
certified
deprecated
blocked
```

Reverse directions and cloud compatibility services require independent packs and evidence.
