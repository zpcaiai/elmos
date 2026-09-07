---
name: platform-high-availability-backup-and-disaster-recovery
description: Validate HA, backup, restore, RPO/RTO, queue/lease recovery, Runner reconnect, and DR for tenant, policy, workflow, audit, Ledger, billing, Artifact, key metadata, license, and offline stores. Use for platform resilience evidence.
---

# Platform High Availability Backup and Disaster Recovery

Read `../references/batch-12-enterprise-platform.md`. Exercise failover and restore under each deployment profile, preserve tenant IDs, reconcile orphan leases/tombstones and prevent duplicate audit, Ledger or Runner results. Include key metadata and offline manifests.

Plans without actual authorized restore evidence do not pass. Task loss, duplicate submission or unmet RPO/RTO blocks T-G.
