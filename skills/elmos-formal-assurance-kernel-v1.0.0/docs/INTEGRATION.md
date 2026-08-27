# Integration into the Elmos Main Repository

## Target mapping

```text
skills/                 → <elmos>/skills/formal-assurance-kernel/
contracts/              → <elmos>/contracts/formal-assurance/
workflows/              → <elmos>/workflows/formal-assurance/
policies/               → <elmos>/policies/formal-assurance/
verifier-adapters/      → <elmos>/verifier-adapters/formal-assurance/
db/migration/           → <elmos>/db/migration/
reference-kernel/       → <elmos>/reference/formal-assurance-kernel/
golden-routes/          → <elmos>/golden-routes/formal-assurance/
deploy/                 → <elmos>/deploy/formal-assurance/
```

The installer is no-overwrite by default. A force install creates a backup and records installed hashes. Uninstall removes only files whose current hash still matches the install manifest.

## Required Elmos ports

- identity: tenant, account, project, actor and roles;
- repository/ChangeGraph: revisions, source maps and change impact;
- durable workflow: submit, checkpoint, pause, resume, cancel, retry;
- billing: reserve, consume, refund and idempotent usage event;
- object storage: immutable tenant-scoped artifacts;
- event bus/outbox: proof, drift and gate events;
- policy: OPA/Rego or equivalent;
- telemetry: OpenTelemetry trace/metric/log;
- deployment gate: P05 authoritative status.

## Integration order

1. Install `core` profile in shadow mode.
2. Apply database migrations in staging and validate RLS.
3. Wire Formal Spec IR and ChangeGraph events.
4. Enable reference gate with synthetic results.
5. Integrate one external verifier at a time through conformance fixtures.
6. Enable a single business-line Golden Route.
7. Move from advisory to blocking only after E1–E4.
8. Enable customer `TRUSTED` claims only after E5.

## Compatibility

The package contracts target PostgreSQL 17, Python 3.11+, Kubernetes 1.30+, OpenTelemetry 1.x, S3-compatible storage and Kafka/NATS/Redpanda-class event buses. Exact production versions are fixed in the release manifest.
