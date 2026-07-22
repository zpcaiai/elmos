---
name: integration-target-profile-and-migration-planner
description: Select and sequence safe target profiles for each integration route, contract, producer, consumer, partner, and workflow. Use when comparing keep, upgrade, managed, API, event, broker replatform, decomposition, workflow extraction, replacement, or retirement paths.
---

# Integration Target Planning

## Decide per asset

Evaluate KEEP_AND_HARDEN, UPGRADE_PLATFORM, MANAGED_EQUIVALENT, API_ENABLE, EVENT_ENABLE, BROKER_REPLATFORM, FLOW_DECOMPOSE, WORKFLOW_EXTRACT, DOMAIN_LOGIC_EXTRACT, PARTNER_REPLATFORM, REPLACE_PLATFORM, and RETIRE independently.

Treat message semantics, transaction, ordering, replay, latency, throughput, payload, consumer count, partner protocol, data residency, availability, security, team capability, license, rollback, and exit plan as constraints.

## State compatibility honestly

Label each candidate SEMANTICALLY_COMPATIBLE, COMPATIBLE_WITH_ADAPTER, REQUIRES_APPLICATION_CHANGE, REQUIRES_REDESIGN, or NOT_RECOMMENDED. Do not force all workloads onto one broker.

Sequence Wave 0 ownership/contracts/trace, Wave 1 bridges/gateway/registry, Wave 2 low-risk consumers, Wave 3 producers and flows, Wave 4 stateful processes and partners, then Wave 5 retirement. Mark a route BLOCKED when no safe path exists.
