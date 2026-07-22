---
name: b37-marketplace-sre-incident-dr-operations
description: "Implement marketplace service catalog SLO on-call incident command capacity backup restore disaster recovery status communication and operational reconciliation."
---

# Skill B37-X13: b37-marketplace-sre-incident-dr-operations

## Use this skill when

- The Batch 37 extension ecosystem requires this lifecycle capability to be production-complete and independently testable.
- A Codex implementation task must create typed contracts, deterministic workflows, evidence, and conservative gates rather than prose-only policy.

## Domain-specific risks and invariants

- Revocation and security containment remain available during degraded commercial or catalog operation.
- Recovery never reactivates revoked releases or duplicates billing/payout events.
- DR uses immutable artifacts and preserves tenant isolation.

## Workflow

1. Inventory catalog, identity, signing, certification, package registry, installation, entitlement, billing, revocation, mirror, and runtime services.
2. Define SLI/SLO, dependencies, error budgets, capacity, recovery objectives, owners, on-call, escalation, and runbooks.
3. Implement backup, restore, cross-region recovery, queue replay, idempotent reconciliation, and status communication.
4. Exercise provider outage, database loss, registry corruption, control-plane outage, signing outage, and region loss.
5. Track postmortems, corrective actions, and recurrent-problem elimination.

## Required repository outputs

- `operations/operations-policy.json`
- service catalog, SLOs, runbooks, incident records, backup/restore and DR evidence

## Verification

- Run `validate_marketplace_operations.py`.
- Perform restore and DR replay with exact RTO/RPO and reconciliation evidence.

## Stop and escalate when

- Critical service has no owner, runbook, backup, or tested recovery.
- Recovery state cannot distinguish current from revoked releases.

## Definition of done

- Marketplace services meet SLOs, incident and DR exercises pass, and all state reconciles after recovery.
