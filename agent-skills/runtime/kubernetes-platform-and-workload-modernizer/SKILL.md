---
name: kubernetes-platform-and-workload-modernizer
description: Design and validate Kubernetes platform and workload contracts, including topology, security, networking, storage, probes, scaling, disruption, backup, upgrades, and tenancy. Use for Kubernetes modernization and policy gates.
---

# Kubernetes Modernizer

## Separate authorities

Model platform concerns—cluster, node pools, CNI, CSI, DNS, gateway, registry, secrets, policy, observability, autoscaling, backup, and upgrade—separately from workload manifests.

Map stateless service to Deployment, stable stateful identity to StatefulSet, node-local infrastructure to DaemonSet, finite task to Job, and scheduled task to CronJob. Do not use DaemonSet as a general service deployment.

## Validation workflow

1. Derive requests, limits, startup, steady, and peak profiles per container from observed evidence.
2. Validate startup, readiness, and liveness semantics; liveness must not restart a service solely because an external dependency is down.
3. Select HPA, VPA, node, event-driven, scheduled, manual, or no scaling while checking downstream capacity.
4. Validate replicas, quorum, zones, nodes, failure domains, anti-affinity, topology spread, PDB scope, graceful termination, and backup.
5. Target Restricted Pod Security for business workloads and require reviewed exceptions for node/platform agents.
6. Start with default-deny ingress and egress, then allow DNS, databases, messaging, observability, and secret providers explicitly.
7. Prove the actual CNI enforces NetworkPolicy; YAML presence is insufficient.
8. Validate storage access mode, zone, performance, encryption, expansion, retention, backup, and restore.

Treat Namespace as an organizational boundary, not a strong tenant boundary. Require independent platform and workload evidence before promotion.

