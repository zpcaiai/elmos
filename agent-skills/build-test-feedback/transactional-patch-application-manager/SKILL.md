---
name: transactional-patch-application-manager
description: "Apply and roll back a Batch 8 patch atomically against a verified Snapshot and generated/manual boundary. Use after policy review approves a structured patch."
---
# Transactional Patch Application Manager
Read `../references/batch-8-repair-loop.md`. Verify base Snapshot and file hashes, apply in an isolated worktree, parse modified files, check boundaries, run minimal static checks, create a candidate Snapshot and retain rollback evidence before promotion.

Reject partial application, stale hashes, manual conflicts, moved declarations, missing generated regions or concurrent overwrite. Do not let an Agent silently resolve a conflict. Restore build files and lockfiles together on rollback.
