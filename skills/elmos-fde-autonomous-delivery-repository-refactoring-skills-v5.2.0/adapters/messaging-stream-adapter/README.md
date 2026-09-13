# messaging-stream-adapter

**Providers:** Kafka/Pulsar/RabbitMQ/cloud queues

**Scope:** topics, schemas, replay, ordering, delivery and side effects.

This directory is an implementation contract, not a live integration. Implement the abstract Elmos port, negotiate capabilities and versions, enforce environment-owned authority, return typed results, and pass every case in `conformance.yaml`. The Adapter never owns semantic truth, routing, or completion.
