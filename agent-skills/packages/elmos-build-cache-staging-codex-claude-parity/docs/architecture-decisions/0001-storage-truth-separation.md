# ADR 0001: Separate immutable artifact truth from mutable orchestration truth

**Status:** Accepted

Immutable bytes and manifests use CAS. Mutable runs, leases, retries, staged-file states, and journal materializations use SQLite/PostgreSQL. Redis is non-authoritative. This enables deduplication, integrity checks, and deterministic recovery.
