---
name: progressive-infrastructure-release-and-environment-promotion
description: Promote immutable VM images, OCI images, IaC modules, charts, overlays, policy bundles, platform versions, serverless revisions, and observability config through governed environments. Use for infrastructure release gates.
---

# Infrastructure Promotion

## Promotion workflow

1. Freeze a content-addressed VM image, container image, IaC module, Helm chart, Kustomize overlay, policy bundle, platform version, serverless revision, or observability configuration.
2. Promote the exact artifact through development, integration, staging, performance, pre-production, production, and DR as applicable; never rebuild for production.
3. Evaluate build, unit, sandbox apply, integration, security, performance, resilience, cost, canary, production, and stability-hold gates.
4. Bind environment-specific configuration and secrets by reference without mutating the artifact.
5. Canary platforms separately from applications: node image, CNI, gateway, mesh, storage driver, and collector changes require platform-specific blast-radius and rollback thresholds.
6. Support canaries by cluster, node pool, namespace, tenant, region, workload, traffic, image, or platform component.
7. Require compatibility, capacity, restore, observability, and cost evidence before promotion.
8. Record every decision and evidence hash in the shared delivery snapshot.

Emergency security promotion requires break-glass, dual approval, reduced scope, a rollback, audit, and deferred validation deadline. A failed gate stops promotion; stability hold remains configurable and evidence-bound.

