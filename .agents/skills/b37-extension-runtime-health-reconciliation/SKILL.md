---
name: b37-extension-runtime-health-reconciliation
description: Implement extension runtime health SLO telemetry desired-versus-actual reconciliation circuit breaking automatic quarantine and fleet-wide version state control.
---

# Skill B37-X02: b37-extension-runtime-health-reconciliation

## Use this skill when

- The Batch 37 extension ecosystem requires this lifecycle capability to be production-complete and independently testable.
- A Codex implementation task must create typed contracts, deterministic workflows, evidence, and conservative gates rather than prose-only policy.

## Domain-specific risks and invariants

- A healthy marketplace listing does not imply a healthy installation.
- Critical policy or tenant-isolation violations trigger immediate quarantine independent of commercial state.
- Reconciliation is idempotent and never silently changes customer-owned configuration.

## Workflow

1. Inventory all active installations, desired release digests, tenant policies, runtime instances, leases, health checks, and current incidents.
2. Define extension-level SLI/SLO for availability, error rate, latency, resource use, evidence production, and policy violations.
3. Implement desired-versus-actual reconciliation for installations, versions, configuration, permissions, and runtime health.
4. Implement circuit breaker, tenant disable, automatic quarantine, rollback trigger, and operator override with audit.
5. Run crash, latency, resource leak, evidence failure, and policy violation drills.

## Required repository outputs

- `runtime/health.json`
- installation reconciliation records, SLO dashboards, quarantine decisions, and drill evidence

## Verification

- Run `validate_runtime_health.py`.
- Prove drift detection, automatic quarantine, recovery, and version convergence in a representative fleet.

## Stop and escalate when

- Health telemetry is missing for a P0 extension.
- Desired and actual state cannot be reconciled without destructive or cross-tenant action.

## Definition of done

- All active installations are reconciled, P0 SLOs pass, critical drift is zero, and quarantine/rollback drills pass.
