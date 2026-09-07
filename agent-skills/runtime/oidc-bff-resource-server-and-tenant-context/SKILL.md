---
name: oidc-bff-resource-server-and-tenant-context
description: "Implement OIDC authentication in the Next.js BFF and Spring Boot resource server, validate JWT issuer/audience, and derive an authenticated tenant candidate without trusting arbitrary tenant headers."
---

# Objective

Implement this authentication path:

Browser
→ OIDC authorization code + PKCE
→ server-side Next.js session
→ Next.js BFF proxy
→ Bearer access token
→ Spring Security resource server
→ verified federated identity
→ tenant membership lookup
→ tenant context candidate

Authentication alone must not grant tenant or resource access.

# Read first

Inspect:

- apps/web authentication dependencies;
- apps/web route handlers;
- apps/web middleware;
- control-api Spring Security configuration;
- application.yml and environment variable handling;
- current tenant header injection;
- local Keycloak or OIDC Compose setup;
- tests for unauthenticated access.

# Backend implementation

## Dependencies

Use the existing Spring Security stack.

Add only the dependencies needed for:

- OAuth2 resource server;
- JWT validation;
- method security;
- security test support.

Do not add a second competing security framework.

## Configuration properties

Introduce typed configuration similar to:

```java
@ConfigurationProperties("elmos.security.oidc")
public record OidcSecurityProperties(
    String issuerUri,
    Set<String> audiences,
    Set<String> allowedAlgorithms,
    Duration clockSkew
) {}
