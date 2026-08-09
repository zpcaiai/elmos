# Sharding and idempotency

Shard by hard isolation and ordering boundaries before balancing preferences. Activities must declare idempotency keys, inputs, outputs, commit tokens, retry class, timeout, resource profile, checkpoint, and compensation. Fan-out and retries are bounded. Workflow versioning must preserve deterministic replay.
