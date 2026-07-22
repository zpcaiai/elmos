---
name: integration-contract-equivalence-validator
description: Validate API, message, schema, delivery, ordering, retry, DLQ, idempotency, partner, workflow, performance, failover, and old/new flow equivalence with controlled virtualization. Use for integration contract tests, negative journeys, virtual-service drift, and semantic comparison.
---

# Integration Contract and Equivalence Validation

## Build the validation matrix

Test API_CONTRACT, MESSAGE_CONTRACT, SCHEMA, DELIVERY, ORDERING, RETRY, DLQ, IDEMPOTENCY, PARTNER, WORKFLOW, PERFORMANCE, and FAILOVER separately. Virtualize only approved APIs, queues, topics, partners, AS2/SFTP endpoints, databases, external services, and human tasks.

Compare headers, payload, schema, key, order, count, duplicates, missing records, delay, routing, side effects, errors, retries, audit, and latency for the same input and initial state.

## Exercise failures

Test crash-before-ack, producer timeout, broker failover, rebalance, duplicate, poison, DLQ, and replay. Test invalid envelopes/signatures, expired certificates, duplicate partner messages, unexpected segments, and missing/delayed acknowledgements. Test workflow timers, compensation, rejection, out-of-order messages, and recovery.

Classify EXACT, SEMANTICALLY_EQUIVALENT, EXPECTED_DIFFERENCE, REGRESSION, or INCONCLUSIVE. Reject stale virtual services and configuration-only similarity as equivalence proof.
