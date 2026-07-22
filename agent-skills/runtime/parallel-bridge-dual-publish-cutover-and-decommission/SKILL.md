---
name: parallel-bridge-dual-publish-cutover-and-decommission
description: Govern compatibility bridges, mirrors, dual publish, producer/consumer/partner/workflow cutover, rollback, stability hold, and legacy platform decommission. Use when migrating between brokers, ESBs, APIs, B2B transports, or workflow engines.
---

# Parallel Migration and Cutover

## Select a bridge

Choose QUEUE_BRIDGE, TOPIC_MIRROR, PROTOCOL_BRIDGE, API_FACADE, EVENT_TRANSLATOR, EDI_DUAL_SEND, FILE_DUAL_DELIVERY, or WORKFLOW_SHADOW. Preserve original and canonical message IDs, source, correlation, causation, schema version, and replay marker.

Prefer transactional outbox, CDC to both platforms, or a governed broker bridge over uncontrolled sequential dual publish. Validate headers, payload, order, transaction, duplicates, retention, errors, and DLQ across platforms.

## Cut over independently

Move consumers, producers, routes, partners, workflows, regions, and tenants through baseline, bridge, shadow, low-risk cohorts, partial traffic, primary switch, stability hold, and legacy-new-use block. Preserve offset and backlog frontiers.

## Retire from runtime evidence

Require zero producers, consumers, partner traffic, workflow instances, and unresolved backlog; resolve DLQ; revoke credentials/certificates; archive configuration; close replay windows; and recover licenses. Record point-of-no-return and rollback side effects before switching.
