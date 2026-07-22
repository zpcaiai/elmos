---
name: github-webhook-ingestion
description: Build or review ELMOS GitHub webhook verification and ingestion. Use for webhook HTTP endpoints, HMAC verification, delivery deduplication, event normalization, retry handling, or webhook audit tests.
---

# GitHub Webhook Ingestion

Keep the public webhook path small: authenticate raw bytes, record the delivery once, normalize a bounded envelope, enqueue work, and return quickly.

## Required workflow

1. Enforce a configured maximum body size before JSON parsing.
2. Verify `X-Hub-Signature-256` as HMAC-SHA-256 over the exact raw request bytes.
3. Compare signatures in constant time and reject missing, malformed, or mismatched signatures.
4. Deduplicate by provider plus `X-GitHub-Delivery` using an atomic unique insert.
5. Store the payload SHA-256, headers needed for audit, minimal normalized fields, receipt time, and processing status.
6. Enqueue downstream work through a port; do not clone or provision a workspace in the request thread.

## Non-negotiable boundaries

- Never verify a parsed or reserialized body.
- Never log payload bodies, signatures, secrets, or authorization headers.
- Treat duplicate delivery as an accepted no-op.
- Unknown event types may be recorded but must not trigger privileged work.
- Rotation must allow an explicit current/previous secret window without accepting an empty secret.

## Acceptance checks

- Include GitHub's published signature test vector and a one-byte mutation test.
- Concurrent duplicate inserts result in one durable delivery.
- Invalid signatures produce no delivery row and no enqueue call.
- The controller accepts raw bytes and returns before long-running work begins.

