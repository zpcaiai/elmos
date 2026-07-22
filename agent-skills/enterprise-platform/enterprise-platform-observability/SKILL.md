---
name: enterprise-platform-observability
description: Correlate Control Plane, Runner, model, policy, quota, billing, audit, SSO, SCIM, and Artifact telemetry with tenant-safe views. Use for platform SLI/SLO, dashboards, alerts, traces, and runbooks.
---

# Enterprise Platform Observability

Read `../references/batch-12-enterprise-platform.md`. Correlate request, tenant, project, run, job, Runner, model call, Artifact and audit IDs; bound label cardinality and redact source, secrets and Prompts. Tenant dashboards expose only tenant data; operators get aggregate health without content access.

Keep Audit and Telemetry responsibilities distinct. Leakage or missing critical observability blocks T-G.
