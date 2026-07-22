---
name: continuous-control-monitoring-risk-exception-and-authorization
description: Monitor control effectiveness, evidence freshness, vulnerabilities, incidents, risk exceptions, conditions, and time-bound internal authorization. Use for continuous reassessment and suspension decisions.
---

# Continuous Internal Authorization

1. Define an authorization boundary containing systems, environments, services, data, infrastructure, dependencies, interconnections, and shared controls.
2. Evaluate threat models, profiles, assessments, open risks, exceptions, incidents, asset versions, data classification, and evidence freshness.
3. Issue only internal `AUTHORIZED`, `AUTHORIZED_WITH_CONDITIONS`, `LIMITED_AUTHORIZATION`, `REASSESSMENT_REQUIRED`, `SUSPENDED`, `DENIED`, or `EXPIRED` decisions with validity and evidence hashes.
4. Make every condition observable and every exception owned, scoped, justified, compensated, approved, time-bound, and automatically expiring.
5. Reassess on source, artifact, dependency, deployment, identity, data, policy, control, critical vulnerability, incident, exception, or standard changes.
6. Permit automation to pause on failed gates or stale evidence, but never to accept critical risk, waive law, sign regulatory authorization, or erase human assessments.

## Acceptance

Internal authorization never claims ISO certification, a SOC report, regulator approval, or formal ATO. Expired or artifact-mismatched decisions cannot authorize deployment.
