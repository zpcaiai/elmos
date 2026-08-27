# Enterprise identity and tenant authorization

ELMOS Web Console uses OIDC Authorization Code + PKCE. Browser JavaScript never
receives the access or refresh token: route handlers store them in Secure,
HttpOnly, SameSite cookies. Repository and operations calls forward the access
token to the control plane, which validates issuer, JWKS signature, expiry and
audience again before enforcing subject, tenant and permission checks.

## Required configuration

Configure the same issuer, JWKS and resource audience for Web Console,
Control Plane and Commercial API. Secrets belong in the deployment secret
provider, not in a checked-in environment file.

```text
ELMOS_OIDC_ISSUER_URI=https://identity.example.com/realms/elmos
ELMOS_OIDC_AUTHORIZATION_ENDPOINT=https://identity.example.com/realms/elmos/protocol/openid-connect/auth
ELMOS_OIDC_TOKEN_ENDPOINT=https://identity.example.com/realms/elmos/protocol/openid-connect/token
ELMOS_OIDC_JWKS_URI=https://identity.example.com/realms/elmos/protocol/openid-connect/certs
ELMOS_OIDC_USERINFO_ENDPOINT=https://identity.example.com/realms/elmos/protocol/openid-connect/userinfo
ELMOS_OIDC_END_SESSION_ENDPOINT=https://identity.example.com/realms/elmos/protocol/openid-connect/logout
ELMOS_OIDC_REVOCATION_ENDPOINT=https://identity.example.com/realms/elmos/protocol/openid-connect/revoke
ELMOS_OIDC_CLIENT_ID=elmos-web-console
ELMOS_OIDC_CLIENT_SECRET=<secret-reference>
ELMOS_OIDC_REDIRECT_URI=https://elmos.example.com/api/auth/callback
ELMOS_OIDC_AUDIENCE=elmos-api
ELMOS_OIDC_SCOPES=openid profile email offline_access
ELMOS_SESSION_SECRET=<at-least-32-random-characters>
ELMOS_PUBLIC_ORIGIN=https://elmos.example.com
```

`ELMOS_OIDC_CLIENT_SECRET` and `ELMOS_SESSION_SECRET` must be injected through
the deployment secret store. Rotation invalidates new exchanges or existing
sealed sessions as appropriate.

`ELMOS_PUBLIC_ORIGIN` is mandatory in production and must contain only the
trusted HTTPS origin (no path, query, fragment or embedded credentials). State
changing session routes compare it with the browser `Origin` and Fetch Metadata
headers instead of trusting a reverse proxy's rewritten request URL.

## Required claims

- `sub`: stable user subject.
- `organization_id`: active tenant. A request cannot override it with headers.
- `roles`: zero or more of `VIEWER`, `DEVELOPER`, `MAINTAINER`, `OPERATOR`,
  `APPROVER`, `TENANT_ADMIN`.
- `permissions`: optional exact permissions. Unknown values and wildcards are
  ignored.
- `elmos_tenants`: optional array of objects with `organization_id`, `roles`
  and `permissions`. Tenant switching is limited to these verified memberships.

The recognized permissions are:

```text
workspace:view
spring:execute
translation:execute
generation:execute
repository:read
repository:write
repository:commit
repository:push
repository:pr
usage:read
billing:write
admin:read
admin:operate
admin:approve
configuration:manage
```

Client-side hiding is only a usability control. The Next.js BFF and Java
control plane independently enforce authorization. Missing, expired, tampered,
cross-tenant or under-privileged sessions fail closed.

## Local fallback

Existing short-lived bearer credentials remain available only outside
production for isolated development and browser fixtures. Production Web
Console routes require an enterprise session; a static shared browser token is
not an accepted production identity.

For a loopback-only browser test account, start the Web Console with
`ELMOS_ALLOW_LOCAL_CREDENTIALS=true` and a 32-character-or-longer
`ELMOS_SESSION_SECRET`. The default local credentials are `test` / `test` and
the default tenant is `local-test`; they can be overridden with
`ELMOS_LOCAL_CREDENTIALS_USERNAME`, `ELMOS_LOCAL_CREDENTIALS_PASSWORD` and
`ELMOS_LOCAL_CREDENTIALS_ORGANIZATION_ID`. The login endpoint rejects
production requests and non-loopback hosts, and the account receives only the
`DEVELOPER` role. Never enable this mode in a deployed or production
environment.

## Verification boundary

Local type checks, Java tests and browser tests are engineering evidence.
External IdP login, refresh rotation, provider revocation, tenant directory
integration, penetration testing and independent review remain `NOT_RUN` until
they execute against an authorized environment.
