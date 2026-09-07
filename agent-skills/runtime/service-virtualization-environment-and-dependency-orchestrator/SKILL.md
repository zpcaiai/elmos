---
name: service-virtualization-environment-and-dependency-orchestrator
description: Orchestrate purpose-fit fakes, stubs, stateful virtual services, containerized real dependencies, sandboxes, fault injection, and leased ephemeral environments. Use for reproducible integration/E2E tests or dependency availability and fidelity problems.
---

# Service Virtualization and Environment Orchestration

## Choose fidelity deliberately

Select in-process fake, static stub, stateful virtual service, containerized real service, shared test service, managed sandbox, or production-like mode from the test purpose. Prefer short-lived real databases, brokers, and caches where their behavior matters. Do not let an over-mocked test claim real-integration evidence.

## Govern virtual services

Bind every virtual scenario to a contract version, state, latency, errors, retries, rates, auth, data, and owner. Compare it with the real provider and classify virtual match, virtual drift, provider unknown, or spec unknown. Invalidate release evidence on drift.

## Lease isolated environments

Allocate namespace, default-deny network, secret references, test-data lease, resources, cost, TTL, and cleanup responsibility. Require tenant/run isolation and conflict/capacity control for shared environments. Preserve failing evidence without preserving secrets.

## Verify readiness and cleanup

Check process, protocol, schema, application, and fixture readiness; a listening port is insufficient. Support bounded timeout, 503, latency, malformed payload, reset, partial response, rate-limit, and ordering faults. Emit a blocking finding when reset or cleanup is not verified.
