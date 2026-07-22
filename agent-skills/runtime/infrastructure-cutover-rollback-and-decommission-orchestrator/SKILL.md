---
name: infrastructure-cutover-rollback-and-decommission-orchestrator
description: Orchestrate frozen infrastructure cutover, DNS and traffic changes, state synchronization, stability hold, rollback, legacy standby, and safe decommissioning. Use for final infrastructure transitions.
---

# Infrastructure Cutover Orchestrator

## Cutover workflow

1. Freeze artifact digests, VM images, IaC commit/state/provider versions, network, DNS, certificates, secret references, observability, cost, and rollback references.
2. Verify target, shadow, synchronization, deployment, internal traffic, canary, traffic shift, full traffic, stability hold, legacy standby, power-off, archive, and decommission as distinct stages.
3. Separate DNS, load balancer/gateway/routes, firewall, compute, platform, middleware, storage, observability, scheduler, and state transitions.
4. Account for TTL, resolver and negative caches, internal/external split horizon, health, old endpoints, and DNS rollback.
5. For stateful workloads, reconcile data, files, queues, sessions, locks, cron, writers, and time before traffic movement.
6. Select route-only, workload, platform, network, state repair, full-environment rollback, or forward fix from fresh evidence.
7. Mark points of no return including incompatible state, globally propagated DNS, license transfer, credential revocation, legacy shutdown, state-format upgrade, state refactor, and deletion.
8. During stability hold, retain bootable legacy, artifacts, enhanced telemetry, rollback validity, visible dual-run cost, and restricted unrelated changes.
9. Before decommission, prove zero traffic/process/unknown consumers, backup, legal hold, license/IP/DNS/certificate/secret/monitoring/CMDB cleanup, and stopped cost.

Every mutating stage requires named approval. Unknown consumers, stale evidence, missing rollback, or absent observation windows block decommission.

