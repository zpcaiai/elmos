# Spring Legacy Modernizer

## Supported problem classes

- old Java/JDK and Spring/Spring Boot versions
- `javax.*` to `jakarta.*`
- XML-heavy configuration and legacy servlet deployment
- deprecated Spring Security configuration
- Hibernate/JPA/MyBatis compatibility
- custom starters, filters, interceptors, proxies, and transactions
- Spring Cloud, Batch, Integration, messaging, scheduling, validation
- obsolete build plugins and dependency conflicts
- missing tests, containers, health, telemetry, SBOM, and release controls
- monolith modularization or strangler boundaries

## Incremental route

```text
snapshot → baseline build/test/API/data/performance/security
→ dependency and risk map
→ target version route
→ JDK/build upgrade
→ Spring/Boot upgrade hops
→ Jakarta/security/data/config changes
→ compile-test-repair
→ differential validation
→ container/telemetry/rollback
→ evidence/readiness
```

## High-risk semantics

- proxy/self-invocation and annotation interception
- bean scopes and lifecycle order
- filter/interceptor/security chain order
- transaction propagation, isolation, retry, and lazy loading
- Jackson and validation defaults
- thread-local security/transaction/request context
- scheduled jobs and duplicate side effects
- database migrations and backward compatibility

OpenRewrite or similar recipes are useful deterministic tools, but they are only one stage in the pipeline.
