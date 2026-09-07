# Event and Distributed Contracts

API, tool and event contracts share versioning, identity, auth, errors, idempotency and compatibility metadata. Event semantics additionally model partitioning, ordering, delivery guarantees, deduplication, replay, schema registry, saga compensation and mixed-version deployment.

Exactly-once is treated as an end-to-end claim over producer, broker, consumer, state and side effects—not a broker configuration label.
