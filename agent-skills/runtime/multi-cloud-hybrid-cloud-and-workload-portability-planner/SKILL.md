---
name: multi-cloud-hybrid-cloud-and-workload-portability-planner
description: Evaluate multi-cloud and hybrid-cloud strategies, workload portability, provider binding, data gravity, control-plane independence, and executable exit plans. Use for cloud placement and recovery planning.
---

# Multi-cloud Portability Planner

## Planning workflow

1. Require a business reason before selecting single cloud, primary-with-DR, cloud by unit/region, best service by workload, hybrid, edge, active-active, or exit-ready single-cloud patterns.
2. Grade portability as provider-locked, rebuildable, artifact-portable, platform-portable, or actively validated.
3. Evaluate runtime, containers, Kubernetes, serverless, database, storage, network, identity, secrets, messaging, observability, data, licenses, regions, egress, and team operations.
4. Classify each binding as portable standard, provider adapter, managed with exit, strategic binding, or hard lock-in.
5. Quantify data volume, growth, latency, consumers, residency, egress, copy time, synchronization, deletion, and encryption.
6. Ensure a provider outage cannot remove login, DNS, secrets, deployment, or DR-switch authority.
7. Prefer signed OCI artifacts, versioned IaC modules, provider-neutral contracts, export formats, and tested backups where appropriate.
8. Define exit format, copy, identity, DNS, keys, secrets, contracts, replacement, cost, duration, and test cadence.

Do not reduce all targets to the lowest common capability. Provider-specific value is allowed when its binding, alternative, exit cost, and recovery are explicit. Recommend active-active only with proven conflict handling, operational readiness, business value, cost approval, and recurring exercises.

