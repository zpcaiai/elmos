---
name: java-project-discovery
description: Discover bounded Java project structure from an immutable ELMOS Snapshot. Use whenever locating Maven or Gradle roots, source sets, modules, wrappers, or mixed-build boundaries for a legacy health check.
---
# Java Project Discovery

## Workflow
1. Require an `AVAILABLE` Snapshot and scan without following symlinks.
2. Exclude VCS metadata, build outputs, IDE state, dependencies, devices and sockets.
3. Enforce file-count, per-file and total-byte limits.
4. Inventory build descriptors, source sets, resources, wrappers and nested roots in stable path order.
5. Emit hashes and mark unreadable or ambiguous roots `INCONCLUSIVE`.

## Acceptance
- Never evaluate a build script during discovery.
- Reject root/path escape and special files.
- Bind output to Snapshot ID and policy hash.

