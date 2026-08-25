# SQLite local-profile notes

Use SQLite in WAL mode with `foreign_keys=ON`, `synchronous=FULL` for control-plane commits, and a busy timeout. Map PostgreSQL UUIDs to text, JSONB to TEXT containing canonical JSON, and partial indexes where supported.

Local artifact bytes still live in filesystem CAS. SQLite stores only metadata, staged-file states, Action Cache mappings, run journal materialization, pins, and checkpoints.

Required startup pragmas:

```sql
PRAGMA journal_mode=WAL;
PRAGMA synchronous=FULL;
PRAGMA foreign_keys=ON;
PRAGMA busy_timeout=5000;
```

Do not share one SQLite file over NFS or other unsupported network filesystems. Team/production deployments use PostgreSQL.
