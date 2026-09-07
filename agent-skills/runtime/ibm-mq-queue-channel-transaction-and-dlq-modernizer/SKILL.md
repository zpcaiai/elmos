---
name: ibm-mq-queue-channel-transaction-and-dlq-modernizer
description: Modernize IBM MQ queue managers, queues, channels, clusters, transactions, message groups, backout handling, RFH2, CCSID, and dead-letter governance. Use when assessing MQ upgrades, managed MQ, REST facades, event bridges, or moves to Kafka or RabbitMQ.
---

# IBM MQ Modernization

## Inventory semantics

Inventory local, remote, alias, transmission, model queues, topics, subscriptions, channels, clusters, listeners, authorities, and DLQs. Capture persistence, expiry, priority, message/correlation/group IDs, sequence, ReplyTo, format, CCSID, encoding, RFH2, selector, and syncpoint.

Classify transactions as LOCAL_UNIT_OF_WORK, XA_TRANSACTION, NO_TRANSACTION, REQUEST_REPLY, or UNKNOWN. Preserve backout count, threshold, queue, poison policy, and manual replay procedures.

## Choose a path

Compare KEEP_MQ, UPGRADE_MQ, MANAGED_MQ, REST_FACADE, EVENT_BRIDGE, QUEUE_TO_KAFKA, QUEUE_TO_RABBITMQ, APPLICATION_REDESIGN, and RETIRE by message semantics.

Treat MQ REST timeouts as ambiguous and require business idempotency. Preserve MQDLH failure reason and original target. Do not claim a REST facade or a topic pair is transactionally equivalent to MQI/JMS request-reply.
