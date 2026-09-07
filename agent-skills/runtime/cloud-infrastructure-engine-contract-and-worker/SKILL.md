---
name: cloud-infrastructure-engine-contract-and-worker
description: Implement the independent cloud and infrastructure modernization engine, capability declaration, provider isolation, Runner routing, and shared ELMOS job contract. Use for infrastructure engine APIs, leases, credentials, regions, provider adapters, or execution boundaries.
---

# Cloud Infrastructure Engine

## Contract

Declare `ELMOS_INFRASTRUCTURE` capabilities for bare metal, VM, private/public cloud, containers, Kubernetes, serverless, IaC, networks, observability, FinOps, resilience, multi-cloud, cutover, and decommissioning.

Expose only the shared engine endpoints: capabilities, scan, plan, execute-step, validate, job lookup, and cancellation. Keep the Worker independently deployable from language engines and the control plane.

## Execution workflow

1. Validate organization, immutable input references, idempotency key, region, and requested capability.
2. Acquire a short-lived job lease and provider-scoped credential through the existing secret broker.
3. Route to a capability-matched Provider Runner.
4. Permit discovery only with read-inventory, read-metrics, read-configuration, read-cost, and log-metadata permissions.
5. Require an immutable Plan, policy decision, cost estimate, security result, named approval, and rollback reference before every write.
6. Capture provider request IDs, resource identities, timestamps, costs, and evidence hashes.
7. Revoke credentials, clean temporary resources, and finalize evidence.

## Boundaries

Keep AWS, Azure, GCP, VMware, KVM, Hyper-V, and platform SDK objects inside replaceable adapters. Store canonical compute, network, storage, identity, secret, registry, Kubernetes, serverless, observability, and cost contracts in core models.

Default-deny create, update, delete, IAM, public exposure, DNS, traffic, key rotation, and production apply. Never infer success from generated IaC, manifests, or a provider request without independent validation. Return a terminal structured failure when the Runner, lease, approval, or evidence authority is unavailable.

Emit only content-addressed Evidence compatible with ELMOS Risk, Check, Cost, Audit, Billing, and Delivery authorities.

