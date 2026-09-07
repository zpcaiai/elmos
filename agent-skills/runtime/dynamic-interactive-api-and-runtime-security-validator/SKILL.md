---
name: dynamic-interactive-api-and-runtime-security-validator
description: Plan and validate DAST, API, authentication, authorization, business-logic, fuzz, IAST, and runtime security tests. Use only for explicitly authorized targets and bounded environments.
---

# Dynamic Security Validation

1. Require target, environment, owner, time window, allowed and prohibited methods, rate/size limits, abort, cleanup, and audit before active testing.
2. Prefer ephemeral, integration, staging, or pre-production. Apply non-destructive, rate-limited, monitored profiles with known accounts for any production-safe assessment.
3. Test login, MFA, reset, token/session lifecycle, horizontal and vertical authorization, object/function/field access, and cross-tenant isolation.
4. Compare documented, observed, shadow, deprecated, admin, and internal API endpoints.
5. Model abuse cases for replay, duplicate payment/refund, race, approval bypass, negative values, and unsafe upload; require human validation for critical business logic.
6. Report runtime coverage only for exercised paths and bound fuzzing to schema, time, memory, nesting, payload, and side effects.

## Acceptance

Block unauthorized production targets, preserve audit, separate automated scans from penetration testing, and never infer untested path safety.
