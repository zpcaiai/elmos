---
name: api-gateway-policy-lifecycle-and-facade-modernizer
description: Modernize API gateway routes, backends, security, rate limits, transformations, products, consumers, versions, canaries, policy drift, and facades. Use for gateway migrations, API sunset, compatibility routing, or progressive traffic shift design.
---

# API Gateway Modernization

## Keep the boundary narrow

Use gateways for protocol, authentication, authorization, rate limits, routing, basic transformation, API products, and observability. Move pricing, approval, core state, long processes, and data ownership to their domain owners.

Inventory host, path, method, backend, auth, rate, quota, cache, retry, timeout, circuit breaker, CORS, TLS/mTLS, logging, analytics, consumer credentials, versions, environments, and last-seen usage.

## Govern lifecycle

Track DRAFT, PUBLISHED, ACTIVE, DEPRECATED, SUNSET_SCHEDULED, SUNSET, and RETIRED. Compare source, desired, runtime, and observed policies. Design canaries by weight, header, consumer, tenant, region, key, or internal cohort with independent gates.

Block route deletion while any unknown or external consumer remains. Verify executed behavior; configuration similarity alone does not prove policy enforcement.
