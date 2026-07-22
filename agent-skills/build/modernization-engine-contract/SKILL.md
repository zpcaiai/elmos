---
name: modernization-engine-contract
description: Define and evolve the versioned ELMOS control-plane to modernization-engine API, OpenAPI, JSON schemas, idempotency behavior, stable errors, capability discovery, and compatibility tests. Use for scan, plan, execute-step, validate, job, cancellation, or future language-engine integration.
---

# Modernization Engine Contract

## 稳定接口

Maintain GET /engine/v1/capabilities; POST /scan, /plan, /execute-step, /validate; GET /jobs/{jobId}; and POST /jobs/{jobId}/cancel.

Require organizationId, snapshot/workspace references, correlationId, and idempotencyKey on side-effecting work. Never transmit long-lived Git tokens, login passwords, cloud credentials, unrestricted host paths, or control-plane database credentials.

## 版本与错误

- Version the URL by API major and each schema independently.
- Add fields compatibly and make clients ignore unknown fields.
- Preserve stable error codes and include retryable, evidenceRefs, sanitizedLogRef, and suggestedAction.
- Preserve the raw engine schema version in the control plane.
- Reuse an existing result for a repeated idempotency key; never duplicate PRs, workspaces, or credits.
- Include UNKNOWN handling for extensible enums.

## 执行步骤

1. Update Java contract types, OpenAPI, and JSON schemas together.
2. Validate request trust boundaries and executor types.
3. Implement the application Port before a language-specific adapter.
4. Add serialization, unknown-field, error, and idempotency contract tests.
5. Confirm the Java Engine remains independently deployable.
6. Record compatibility impact and generated evidence.

## 验收与失败处理

Require parseable OpenAPI, passing contract tests, backward-compatible fields, stable errors, and no secret-bearing fields. On incompatibility, introduce a major version or retain the old field; never silently reinterpret a field.

