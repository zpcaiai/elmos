---
name: github-webhook-ingress-idempotency-redelivery-and-event-f6d65b3a
description: "Implement raw-body GitHub webhook validation, durable receipt, delivery idempotency, asynchronous normalization, redelivery, schema versioning, dead-letter handling, and security events."
---

# Objective

Turn GitHub webhooks into durable, idempotent facts without blocking the
GitHub delivery request.

# Security filter chain

Webhook endpoint uses a dedicated authentication path.

It does not use a human OIDC session.

Required:

- HTTPS;
- provider-specific webhook secret;
- raw body HMAC verification;
- payload size limit;
- content-type validation;
- request timeout;
- optional approved IP policy as defense in depth;
- no tenant selected from payload alone.

# Endpoint

Recommended:

```text
POST /webhooks/github/{providerPublicId}
