---
name: infrastructure-elmos-unified-evidence-integration
description: Map infrastructure estate, placement, supply chain, platform, IaC, network, observability, SLO, cost, resilience, portability, cutover, and decommission results into shared ELMOS Evidence. Use for composite delivery and audits.
---

# Infrastructure Evidence Integration

## Integration workflow

1. Reuse Organization, Repository, System Landscape, Portfolio, Plan, Step, Risk, Approval, Evidence, Delivery Snapshot, Audit, Billing, and Customer Success authorities.
2. Emit `scope=CLOUD_INFRASTRUCTURE`, `engine=ELMOS_INFRASTRUCTURE`, schema version, content-addressed artifact reference, producer, time, organization, and immutable input bindings.
3. Map estate, placement, container build/supply chain, Kubernetes platform/workload, serverless, IaC plan/apply/drift, network, mesh, observability, SLO, cost, resilience, restore, DR, portability, cutover, and decommission evidence.
4. Map local state, privileged containers, IaC drift, observability gaps, SLO failure, missing restore tests, vendor binding, and cost regression to shared risks.
5. Build a Composite Change Set that links application PRs, images, IaC, Kubernetes manifests, routes, policies, observability, budgets, DR, and decommission plans without merging their authorities.
6. Publish independent checks for supply chain, infrastructure plan, Kubernetes policy, network, observability, SLO, budget, resilience, restore, portability, and cutover.
7. Map discovery, image/build, cluster time, serverless validation, resource plan/apply, telemetry, chaos, DR, multi-cloud, and cutover usage into shared cost units.
8. Audit account connections, credential leases, approvals, apply, firewall/public/IAM/secret/DNS/traffic changes, budget overrides, experiments, DR, and deletions.

Container build success cannot satisfy a platform gate. Require offline-verifiable hashes, signatures, provenance, freshness, and independent validation before delivery.

