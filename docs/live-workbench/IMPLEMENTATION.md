# Live Workbench implementation

The pinned source package is stored as inert input at
`skills/subskills/elmos-live-workbench-skills-v1.0.0.zip`; its SHA-256 is
`c7619ce2955b083e39660a159166b6c9b498855203a55b5b8dd3b2cc68d84cfe`.
The matching immutable mirror lives at
`skills/elmos-live-workbench-skills-v1.0.0/elmos-live-workbench/`.

`modules/live-workbench` is the repository-owned `lw.v1` implementation. It
integrates with the existing Batch 36 `modules/developer-workflow`, Product B36
`modules/secure-execution-plane`, and evidence-bound host interfaces. The pure
typed handlers cover all 28 package identities. The Spring production carrier
adds JWT-derived tenant scope, PostgreSQL RLS, immutable catalogs, atomic
three-slot admission, fixed 600-second readiness CAS, durable command/event/
audit/outbox ledgers, unknown-result reconciliation, resource cleanup receipts,
SSE cursor replay, evidence-first explanations, private assessment dispatch,
and exact provider boundaries. `apps/web-console/app/workbench` supplies the
authenticated administrator browser surface through a server-only BFF.

The implementation is deliberately unable to mint authority, execute a shell
command, launch an untrusted process, open a public debug port, accept a client
`passed=true`, extend a preview lease, or issue a certification result. Provider
secrets are file-mounted, provider calls are HMAC-bound and time-bounded, and
preview URLs are restricted to configured HTTPS origins and the session expiry.

`HANDLER_MAP.json` is the reviewed exact mapping from each imported Skill
identity to a concrete, typed service method. The archive validator rejects a
missing, extra, or unmapped identity; it does not treat a catch-all dispatcher
as implementation.

The runtime integration points remain host ports: verified authority, isolated
sandbox/provider, independent readiness verifier, evidence pipeline, and DAP or
CDP adapter. A candidate runtime profile cannot be promoted by JSON or by a
local test. Until a qualified provider and real external evidence are attached,
distributed debugging and native-device laboratories are `BLOCKED_BY_HOST`; all
provider/browser/device/deployment/certification evidence is `NOT_RUN`. The
conservative gate in `scripts/live_workbench/run_production_gate.py` requires
all 18 source acceptance surfaces and independent evidence, and currently
returns `BLOCKED / NOT_CERTIFIED` for the checked-in template.

## Local qualification

```sh
python3 scripts/live_workbench/validate_archive.py
python3 -m unittest discover -s tests/live-workbench -p 'test_*.py'
mvn -q -pl modules/live-workbench -am test
pnpm --dir apps/web-console test:live-workbench-route
pnpm --dir apps/web-console build
```

Set `ELMOS_LW_TEST_DATABASE_URL`, `ELMOS_LW_TEST_DATABASE_USER`, and
`ELMOS_LW_TEST_DATABASE_PASSWORD` to execute the real PostgreSQL lifecycle test
instead of its explicit skip. See `PRODUCTION_RUNBOOK.md` for carrier and
provider configuration.

These checks prove repository-owned implementation and local integration only.
They do not represent 600 seconds of provider runtime, a production isolation
audit, browser/device coverage, deployment qualification, or independent
certification.
