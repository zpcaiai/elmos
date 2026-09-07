---
name: observability-telemetry-slo-and-operational-readiness
description: Establish cross-engine traces, metrics, logs, profiles, events, audits, executable SLIs/SLOs, error budgets, alerts, and operational readiness. Use for OpenTelemetry and infrastructure release gates.
---

# Observability and SLO Readiness

## Telemetry workflow

1. Model trace, metric, log, profile, event, and audit signals separately.
2. Route approved application instrumentation through versioned OpenTelemetry SDK/agents and collectors to approved backends.
3. Preserve W3C trace context across Java, .NET, Python, frontend, database, infrastructure, messaging, and serverless boundaries.
4. Bind semantic-convention version and canonical resource identity: service name/namespace/version, environment, provider/region, cluster/namespace, and host ID.
5. Prohibit credentials, keys, secrets, PII, and full payloads in baggage; redact structured logs and apply retention policies.
6. Define executable SLI source, query, window, good/total events, missing-data treatment, and owner.
7. Define SLO target/window/owner and error-budget state. Unknown or exhausted budgets block high-risk promotion as policy requires.
8. Require actionable alerts with owner, runbook, severity, suppression, dependencies, and resolution criteria.
9. Validate dashboard, on-call, runbook, backup/restore, capacity, dependencies, certificates, cost, and rollback readiness.

A configured collector is not evidence of end-to-end telemetry. Cross-language trace breaks, low coverage, non-actionable alerts, or missing SLO ownership block full cutover.

