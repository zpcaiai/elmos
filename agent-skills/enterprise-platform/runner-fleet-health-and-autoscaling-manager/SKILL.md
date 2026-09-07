---
name: runner-fleet-health-and-autoscaling-manager
description: Manage SaaS, dedicated, private, and offline Runner fleet health, capacity, version drift, quarantine, autoscaling, drain, and rolling upgrades. Use for fleet operations or queue SLO planning.
---

# Runner Fleet Health and Autoscaling Manager

Read `../references/batch-12-enterprise-platform.md`. Scale by queue/capability/reservation within tenant quota; drain before upgrade, checkpoint recoverable work, verify signed version/attestation/self-test and revoke identity before removal. Dedicated capacity never serves another tenant.

Unhealthy, unsafe-version or disk-exhausted Runners cannot claim work. Feed health and recovery evidence to T-C/T-G.
