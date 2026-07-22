---
name: canonical-integration-contract-route-and-message-ir
description: Convert vendor ESB, broker, API, EDI, file, and workflow assets into the Canonical Integration IR. Use when normalizing routes, messages, delivery semantics, transformations, stateful flows, and unresolved vendor behavior before target generation.
---

# Canonical Integration IR

## Normalize without losing semantics

Represent route steps as SOURCE, DECODE, AUTHENTICATE, AUTHORIZE, VALIDATE, TRANSFORM, ENRICH, FILTER, ROUTE, SPLIT, AGGREGATE, INVOKE, PUBLISH, PERSIST, RETRY, COMPENSATE, or SINK.

Represent message envelope, headers, payload schema, key, correlation, causation, timestamps, identity, trace, security, and classification independently. Make delivery, ordering, retry, dead-letter, and idempotency policies explicit.

## Preserve uncertainty

- Separate protocol behavior from business rules.
- Model state, persistence, correlation, timeout, retry, compensation, and human action for stateful flows.
- Retain source product, object version, vendor configuration, and unsupported semantics.
- Mark dynamic routes STATIC_RESOLVED, CONFIG_RESOLVED, RUNTIME_OBSERVED, PARTIAL, or UNRESOLVED.

Never transform flows with regular-expression replacement. Emit target candidates only after the IR identifies unresolved semantics and evidence lineage.
