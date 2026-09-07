---
name: system-cutover-rollback-and-decommission-orchestrator
description: Orchestrate evidence-bound system cutover, data-aware rollback, stability hold, legacy read-only, and decommission readiness. Use only after composite validation gates are assembled.
---

# System Cutover, Rollback, and Decommission Orchestrator

## Freeze

Freeze repository commits, artifact digests, contract snapshot, compatibility runtime, data frontier, traffic plan, validation profile, rollback plan, approvals, and evidence. Revalidate on any drift.

## Workflow

1. Execute explicit check, approval, deploy, configure, sync, lag, reconciliation, traffic, read, write, verify, hold, rollback, and decommission steps through external approved ports.
2. Require human approval for production writes and destructive or irreversible operations.
3. Classify rollback as reversible, reversible with repair, forward-fix only, or irreversible. If legacy cannot read new writes and no reverse CDC/approved repair exists, choose forward fix; never pretend a traffic rollback repairs data.
4. Hold stability with elevated observability while preserving legacy artifacts, compatibility runtime, and rollback capability.
5. Require zero legacy traffic, consumers, database writes, and batch access; credential revocation; archive/legal/audit retention; evidence pack; owner/cost approval; CMDB update; and completed stability hold before decommission readiness.

## Boundary

The skill emits plans and decisions, never deletes a database or auto-decommissions an asset.
