---
name: messaging-producer-consumer-migrator
description: "Migrate framework messaging producers, consumers, queues, brokers, schemas, acknowledgement, delivery, retry, DLQ, ordering, and shutdown. Use for event, command, job, stream, or request-response messaging conversion."
---
# Messaging Producer and Consumer Migrator
Read `../references/afsm-v1.md`. Preserve broker/destination/group/key/header/schema, ack/commit, delivery, order, concurrency, retry/backoff/DLQ, poison handling, idempotency, transaction/outbox, rebalance and drain behavior.

Classify request-local background work separately from durable messaging. State broker, producer, consumer and transaction guarantees rather than claiming absolute exactly-once. Block delivery downgrade, missing ack/idempotency or unsafe shutdown.

