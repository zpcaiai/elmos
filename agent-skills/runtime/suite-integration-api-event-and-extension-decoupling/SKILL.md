---
name: suite-integration-api-event-and-extension-decoupling
description: Decouple enterprise suites from direct tables, database links, screen automation, internal APIs, shared credentials, and point-to-point integrations. Use when moving SAP, Oracle, Dynamics, Dataverse, or Salesforce boundaries to supported APIs, events, facades, CDC, EDI, MFT, or governed adapters.
---

# Suite Integration Decoupling

## Execute

1. Inventory direct table reads and writes, database links, screen automation, internal APIs, files, custom RPC, shared credentials, and point-to-point links.
2. Select supported API, business event, change event, BFF, domain facade, EDI, MFT, CDC, or integration adapter by semantics.
3. Keep core, extension, integration API, event, data export, and batch interface contracts distinct.
4. Preserve identity context, authorization boundary, idempotency, ordering, delivery, retry, business result, and data authority.
5. Minimize DTOs and prevent internal suite states and fields from leaking into external contracts.
6. Give every compatibility window an owner, observed usage, version, expiry, adapter, removal task, and evidence.

## Guardrails

Do not access SaaS databases, build long-term contracts on unpublished APIs, copy business rules into gateways, dual-write without recovery, or retire interfaces while unknown consumers remain. Coordinate contract and message semantics with the Enterprise Integration engine.
