---
name: multi-tenant-isolation-profile-planner
description: Select and verify multi-tenant isolation levels across identity, data, compute, network, model, key, backup, logs, and support. Use for shared, namespace, dedicated-cluster, dedicated-installation, or air-gapped tenancy design.
---

# Multi-tenant Isolation Profile Planner

Read `../references/batch-12-enterprise-platform.md`. Map contract sensitivity to Levels 1–6, then document isolation and Noisy Neighbor controls for every dimension. Require dedicated keys and Runner capacity where declared; backup and support isolation cannot be weaker than online access.

Emit an isolation matrix and test obligations. Any leak, shared dedicated key, client-overridable filter or contract/deployment mismatch blocks T-A.
