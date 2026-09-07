---
name: kafka-topic-partition-consumer-and-stream-modernizer
description: Govern Kafka clusters, topics, partitions, keys, consumer groups, offsets, transactions, Connect, streams, replay, retention, and compaction. Use for Kafka upgrades, managed moves, broker bridges, topic redesign, or MQ-to-Kafka assessment.
---

# Kafka Modernization

## Establish the topic contract

Record topic purpose, owner, producer, consumers, key, schema, retention, compaction, classification, SLA, and replay policy. Inventory brokers, controller, partitions, replicas, ISR, consumer groups, offsets, connectors, stream applications, ACLs, and quotas.

## Preserve ordering and delivery

- Treat ordering as partition-scoped. Require a stable key for entity order.
- Record source and target groups, start offset, timestamp mapping, replay window, duplicate strategy, and cutover frontier.
- Distinguish producer idempotence, Kafka transaction, Kafka Streams EOS, external side-effect idempotency, and end-to-end verification.
- Test rebalance, lag, retry, duplicates, poison messages, replay, compaction, tombstones, and consumer side effects.

Do not equate Kafka retention with legal data retention. Block unknown consumers, unstable keys, unbounded lag, ungoverned schemas, and non-idempotent replay.
