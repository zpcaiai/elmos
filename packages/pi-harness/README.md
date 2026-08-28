# Elmos PI Harness 5.1

This is the repository-owned implementation of the executable core described by
`elmos-pi-harness-architecture-v5.1.0.zip`.  The ZIP is retained as untrusted
source material; its installers, scripts, SQL, prompts, and workflow documents
are not executed by this implementation.

Implemented runtime guarantees:

- environment/attachment-owned authority snapshots with upper-policy intersection;
- explicit tenant and actor context, tenant-scoped durable reads and writes;
- append-only task events, bounded replay, idempotency, branch, pause/resume/cancel;
- executor replacement and generation fencing for callbacks and tool results;
- durable workspace ownership, heartbeats, and checkpoint-gated stale takeover;
- typed tool results (text/media/encrypted/unknown) without adapter stringification;
- protocol/schema negotiation and adapter boundary types;
- content-addressed artifact storage with atomic writes;
- provider-neutral benchmark campaigns where only an external verifier can set success;
- conservative evidence decisions that never manufacture certification.

Run locally:

```bash
make -C packages/pi-harness test
make -C packages/pi-harness demo
```

The standard-library HTTP server is suitable for a single-node controlled
deployment. Production installations must provide a non-empty API token and a
TLS/mTLS-capable ingress, use a managed database/object store, and supply real
independent verifier, provider, disaster-recovery, and customer-acceptance
evidence. Those external gates remain `NOT_RUN` here by design.
