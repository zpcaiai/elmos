---
name: integration-elmos-unified-evidence-integration
description: Map enterprise integration estate, contracts, broker, gateway, B2B, workflow, security, observability, replay, equivalence, cutover, and decommission results into shared ELMOS Evidence, Risk, Portfolio, Checks, Audit, and offline evidence packs.
---

# Unified Integration Evidence

## Normalize evidence

Emit `scope=ENTERPRISE_INTEGRATION`, `engine=ELMOS_ENTERPRISE_INTEGRATION`, schema `elmos.enterprise-integration-evidence.v1`, immutable artifact references, source identity, engine version, policy version, and external execution status.

Map estate, route graph, producer/consumer matrix, message/event contracts, schema compatibility, ESB, IBM MQ, Kafka, RabbitMQ, API Gateway, partner, workflow, security, observability, equivalence, cutover, and decommission evidence separately.

## Map risk and checks

Map unknown consumers, ordering change, partial dual publish, breaking schema, DLQ backlog, partner acknowledgement failure, and workflow state loss into shared risk codes. Publish separate checks for estate, contract, delivery, schema, gateway, broker, partner, workflow, replay, and cutover.

Audit queue/topic creation, compatibility-mode change, producer switch, offset change, replay, DLQ replay, certificate rotation, route change, dual publish, workflow state migration, and deletion. Keep contract, delivery, and business-result gates distinct and make the Evidence Pack verifiable offline.
