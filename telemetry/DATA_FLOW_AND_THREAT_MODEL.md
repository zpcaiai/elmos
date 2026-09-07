# Telemetry data flow and threat model

## Data flow

1. The browser collector creates allow-listed technical events and can be opted
   out. Generic field changes are never collected; interaction events require an
   explicit stable `data-operation-id`.
2. The same-origin Next.js ingress validates the exact schema, strips query strings,
   rate limits the anonymous HMAC session and forwards through an internal lease.
3. `product_telemetry_events` stores pseudonymous, tenant-RLS-scoped technical data.
4. The Web BFF and control-plane interceptors independently append server operation
   attempts/results to immutable `audit_events`; user telemetry opt-out does not
   disable this security audit.
5. SLO evaluation reads the union without copying raw input and creates alerts,
   incidents, notification outbox rows and digest-bound remediation proposals.
6. Authorized retention deletes only expired `product_telemetry_events`, records
   aggregate evidence, and never deletes `audit_events`.

## Threats and controls

| Threat | Control |
| --- | --- |
| Secret, prompt, source or personal-data leakage | Exact allow-list, body/query/error-text prohibition, client and server validation |
| Tenant crossover | Transaction-scoped PostgreSQL RLS and configured tenant binding |
| Caller role escalation | Server-side token-to-role mapping; browser cannot set the trusted role |
| Missing operations | BFF durable attempt audit plus control-plane attempt/completion interceptor |
| Log recursion | Telemetry/audit ingestion routes are excluded from their own server interceptors |
| Unbounded cardinality/cost | Stable route templates, stable error codes, bounded batch, dimensions, windows and row limits |
| Employee surveillance or misleading click metrics | No field-change capture, no raw control labels, explicit operation IDs only, and workflow outcome metrics exclude clicks/page views |
| Automated unsafe source changes | Automation stops at previewable digest-bound SCM plan; approval and external SCM/test/deploy remain separate |
| Retention weakens audit | Product telemetry and immutable security audit are separate tables and lifecycles |
| Stale workflow writes | Every admin mutation requires an expected version and fails with conflict on drift |

External notification delivery, production-scale capacity, privacy review and
deployment evidence remain `NOT_RUN` until executed in the authorized target.
