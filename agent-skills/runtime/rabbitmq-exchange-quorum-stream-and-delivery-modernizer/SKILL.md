---
name: rabbitmq-exchange-quorum-stream-and-delivery-modernizer
description: Modernize RabbitMQ virtual hosts, exchanges, bindings, Classic, Quorum, Stream, acknowledgements, confirms, requeue, poison, and dead-letter behavior. Use for RabbitMQ 4 upgrades, queue-type selection, federation, shovel, or delivery troubleshooting.
---

# RabbitMQ Modernization

## Inventory routing and delivery

Inventory vhosts, direct/topic/fanout/headers/custom exchanges, queues, queue types, bindings, routing keys, consumers, publishers, policies, federation, shovel, DLX, TTL, limits, and permissions.

Choose CLASSIC, QUORUM, or STREAM by workload. Treat Quorum as replicated work-queue storage and Stream as retained repeatable-read messaging. Do not preserve mirrored Classic queues in RabbitMQ 4.x.

## Validate migration

Test declarations, feature differences, priorities, publisher confirms, consumer ack/nack/reject, requeue, delivery limits, poison handling, DLX, throughput, disk, replica behavior, and retention. Detect requeue loops, unbounded queues, missing confirms, unknown acknowledgement semantics, ownerless DLX, and undefined Stream retention.
