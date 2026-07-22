---
name: repository-snapshot-manager
description: Build or review immutable ELMOS repository snapshots, deterministic tar.zst archives, file manifests, commit resolution, and artifact retention. Use for snapshot domain code, source fetchers, archive generation, or snapshot schemas.
---

# Repository Snapshot Manager

Convert a requested ref into a content-addressed, immutable input before any modernization work starts.

## Required workflow

1. Resolve the requested ref to a full commit SHA and record provider/repository provenance.
2. Fetch into an isolated staging directory without retaining SCM credentials.
3. Reject path traversal, escaping symlinks, device files, sockets, and unsupported special entries.
4. Exclude `.git` and configured secret/build-output patterns.
5. Produce a sorted manifest with path, type, mode, size, and SHA-256.
6. Build deterministic `tar.zst` bytes with normalized owner/group/timestamps and sorted paths.
7. Store by digest, then atomically mark the snapshot available; never mutate an available snapshot.

## Non-negotiable boundaries

- A branch or tag is not an immutable snapshot identity; the resolved commit SHA is required.
- Artifact digest, manifest digest, byte size, archive format, creation status, and provenance are mandatory.
- Archive output must not depend on checkout path, wall clock, uid, or gid.
- Partial uploads remain failed/incomplete and must never be consumed.

## Acceptance checks

- Two archives of the same tree have identical SHA-256 values.
- Tests cover `.git` exclusion, secret-pattern exclusion, symlink escape, and traversal rejection.
- Snapshot state transitions are monotonic and immutable after `AVAILABLE`.
- Schema and database constraints require full digests and resolved commit identity.

