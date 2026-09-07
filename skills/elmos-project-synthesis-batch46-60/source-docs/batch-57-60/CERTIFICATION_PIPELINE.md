# Certification Pipeline

## Gate 1 — Full-stack assembly

- Frontend contracts resolve to exact backend contract versions.
- Authentication callbacks, CORS, tenant context, and permission visibility are consistent.
- Critical journeys are wired through public boundaries.

## Gate 2 — Verification completeness

- Every must-have criterion has a verification obligation.
- High-risk requirements include negative, security, resilience, and recovery tests.
- Test data is synthetic, deterministic, tenant-isolated, and privacy-safe.

## Gate 3 — Build Green

- Clean isolated build or install succeeds.
- Unit, integration, contract, migration, and required E2E tests pass.
- Application starts and reaches readiness.
- Authenticated smoke succeeds and unauthorized smoke fails.
- Required environment matrix cells pass.
- Repairs remain bounded and policy-compliant.

## Gate 4 — Production delivery

- CI and branch protection enforce mandatory gates.
- SAST, SCA, license, secret, container, IaC, and policy checks pass.
- Image is non-root, signed, and linked to SBOM and release manifest.
- Kubernetes or target platform deployment validates.
- Telemetry and SLO controls are active.
- Canary/blue-green promotion and abort are defined.
- Rollback, restore, replay, and DR exercise requirements exist.
