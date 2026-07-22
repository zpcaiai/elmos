---
name: patch-audit-rollback-and-evidence-manager
description: "Record Batch 8 patch provenance, diff, validation, approval, Snapshot chain, evidence, and rollback. Use for every prepared, applied, rejected, conflicted, or rolled-back patch."
---
# Patch Audit Rollback and Evidence Manager
Read `../references/batch-8-repair-loop.md`. Preserve author kind/ID, cluster/plan, files/declarations, before/after Snapshots, Diagnostic sets, diff, compile/test logs, source maps, Agent context/output summary, approvals and rollback command/evidence.

Distinguish Agent and human changes, retain failed patches, redact secrets and create rollback information before commit. Never overwrite audit history or publish a final change without evidence references.
