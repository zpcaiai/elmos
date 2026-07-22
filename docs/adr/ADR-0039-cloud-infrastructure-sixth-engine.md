# ADR-0039: Cloud and infrastructure modernization as a sixth execution engine

## Status

Accepted for Batch 16 on 2026-07-21.

## Context

A Dockerfile, Kubernetes manifest, or IaC plan does not prove that a workload is cloud-native, secure, observable, affordable, resilient, portable, or safely cut over. Infrastructure discovery and mutation also require broader credentials and blast-radius controls than language transformation. Embedding cloud SDKs in language engines or the control plane would combine execution and approval authorities.

## Decision

Add an independently deployable Java 21 `ELMOS_INFRASTRUCTURE` worker. Reuse the shared Engine API, Tenant, Workflow, Secret Lease, Runner, Risk, Approval, Evidence, Portfolio, Delivery, Audit, Billing, and Composite authorities.

Keep four tracks: VM modernization, container/Kubernetes, serverless/event-driven, and cloud infrastructure governance. Compare bare metal, VM, container, Kubernetes, serverless, managed, edge, and retirement targets. Treat license, hardware, state, latency, residency, team capability, cost, and exit as explicit constraints; Kubernetes is not the default.

Keep cloud, hypervisor, SSH/WinRM, image builder, container builder, Kubernetes, OpenTofu/Terraform-compatible, serverless, observability, cost, chaos, and multi-cloud implementations behind replaceable Provider/Runner ports. Discovery defaults to read-only. Core models remain provider-neutral and preserve vendor bindings through extensions.

Require Discovery → Desired State → immutable Plan → Policy/Cost/Security → named Approval → Apply → independent Validation → Evidence for every write. Production apply, IAM/public exposure, DNS/traffic changes, chaos, failover, deletion, and decommission can never be automatic merely because an Agent or provider reports success.

## Consequences

- The control plane adjudicates evidence but never calls a provider or opens host sessions.
- IaC import must reach an explained no-change baseline before refactoring.
- Container build, Kubernetes platform, network enforcement, SLO, cost, restore, resilience, portability, cutover, and decommission remain separate gates.
- V16 creates 96 tenant-scoped projections and reuses four existing SLO/backup/restore/DR authorities.
- I001–I016 and 26 deterministic incident scenarios define the repository acceptance minimum.
- Unit tests and fixtures never prove a customer cloud change, workload migration, DR recovery, saving, cutover, rollback, or resource deletion.

## External gates

Customer accounts/datacenters, approved scopes, provider and hypervisor credentials, Runner images, private networks, representative workloads, target subscriptions/projects, registries, clusters, serverless platforms, IaC backends, cost exports, telemetry backends, business SLO/RTO/RPO owners, chaos approvals, restore environments, DR capacity, DNS/traffic authority, license owners, and decommission approval remain `NOT_CONFIGURED` or `NOT_RUN` until supplied and independently verified.
