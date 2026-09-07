---
name: resilience-chaos-backup-disaster-recovery-engine
description: Model failures, business-sourced RTO/RPO, safe chaos experiments, backup and restore, regional disaster recovery, game days, and resilience evidence. Use for resilience and continuity validation.
---

# Resilience and Disaster Recovery

## Resilience workflow

1. Model process, pod, node, zone, region, network, latency, loss, DNS, certificate, dependency, database, queue, storage, compute, cloud API, and identity failures.
2. Require workload criticality, availability, business/contract/compliance/BIA-sourced RTO and RPO, degraded mode, dependencies, quorum, retry, timeout, circuit, bulkhead, queue, backup, and failover.
3. Never invent RTO or RPO.
4. Define chaos hypothesis, approved environment, blast radius, duration, observers, abort conditions, rollback, and irreversible-data protections.
5. Prefer non-production experiments; require explicit elevated authorization for production.
6. Track proposed, reviewed, approved, scheduled, running, aborted, completed, and failed states.
7. Back up databases, objects, volumes, IaC state, cluster config, secret metadata, certificates, registry, evidence, and audit according to policy.
8. Prove recoverability with periodic restore tests; backup job success alone is insufficient.
9. Validate backup/restore, pilot light, warm standby, active-passive, active-active, and distributed modes against data, DNS, identity, certificates, artifacts, secrets, networking, capacity, quotas, dependencies, and operations.
10. Emit game-day timeline, decisions, recovery evidence, and owned action items.

Separate zone and region evidence. Abort safely and return inconclusive rather than fabricating resilience.

