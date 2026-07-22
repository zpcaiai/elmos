# ADR-0048: Enterprise Integration and Middleware Engine

## Status

Accepted for Batch 20 repository scope on 2026-07-21.

## Decision

Add `ELMOS_ENTERPRISE_INTEGRATION` as the tenth independent execution engine. Reuse the existing tenant, workflow, authorization, evidence, quality, audit, billing, delivery, SCM, portfolio, and cutover control planes. Do not create a second platform around ESB or broker products.

Normalize ESB/SOA routes, message and event contracts, delivery/ordering/idempotency policies, broker resources, API gateway policy, partner agreements, file transfers, and workflow state into a vendor-neutral Integration Estate and Canonical Integration IR. Keep vendor extensions and unresolved runtime semantics visible.

Select IBM MQ, Kafka, RabbitMQ, API Gateway, B2B/MFT, or Workflow targets by message and process semantics rather than imposing one broker. Separate commands, events, notifications, queries, contracts, transport acknowledgement, delivery result, and business result. Limit exactly-once claims to the proven boundary.

External adapters default to read-only and `NOT_CONFIGURED`. Require short-lived leases, resource scopes, partner/replay authorization, and independent production approval. The Worker cannot purge queues, reset offsets, delete topics, change partner certificates, replay production messages, create public routes, switch producers, accept loss, or mutate Cutover/Decommission decisions.

Use Flyway V21 for Batch 20 because V20 is already the enterprise commercial-loop migration. Create 70 new strong-RLS integration projections and extend the four existing authorities `message_brokers`, `message_contracts`, `message_contract_versions`, and `file_contracts` rather than duplicating them.

## Consequences

Repository tests can prove contracts, deterministic policy, tenant and idempotency boundaries, fail-closed adapters, Skill integrity, and independent decision logic. They cannot prove a customer ESB or broker estate, partner interoperability, live replay, semantic equivalence, production cutover, or decommission. Those remain external evidence gates.
