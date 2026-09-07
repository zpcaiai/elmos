# ADR-0010: Immutable repository snapshot format

Status: Accepted

## Decision

Each requested ref is resolved to a full commit and captured once as deterministic `tar.zst`. Archive paths are sorted; uid, gid, names, and timestamps are normalized; `.git`, configured secrets, escaping links, and special files are excluded or rejected. Archive and manifest SHA-256 values form the content identity.

## Consequences

Available snapshots are immutable and reusable. Partial or unverified artifacts cannot be materialized.
