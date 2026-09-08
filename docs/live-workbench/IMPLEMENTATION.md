# Live Workbench implementation

The pinned source package is stored as inert input at
`skills/subskills/elmos-live-workbench-skills-v1.0.0.zip`; its SHA-256 is
`c7619ce2955b083e39660a159166b6c9b498855203a55b5b8dd3b2cc68d84cfe`.
The matching immutable mirror lives at
`skills/elmos-live-workbench-skills-v1.0.0/elmos-live-workbench/`.

`modules/live-workbench` is the repository-owned `lw.v1` implementation. It
integrates with the existing Batch 36 `modules/developer-workflow` module and
provides typed contracts and tests for all 28 package identities. The core is
deliberately unable to mint authority, execute a shell command, launch an
untrusted process, open a public debug port, extend a preview lease, or issue a
certification result.

`HANDLER_MAP.json` is the reviewed exact mapping from each imported Skill
identity to a concrete, typed service method. The archive validator rejects a
missing, extra, or unmapped identity; it does not treat a catch-all dispatcher
as implementation.

The runtime integration points remain host ports: verified authority, isolated
sandbox/provider, independent readiness verifier, evidence pipeline, and DAP or
CDP adapter. A candidate runtime profile cannot be promoted by JSON or by a
local test. Until a qualified provider and real external evidence are attached,
distributed debugging and native-device laboratories are `BLOCKED_BY_HOST`; all
provider/browser/device/deployment/certification evidence is `NOT_RUN`.

## Local qualification

```sh
python3 scripts/live_workbench/validate_archive.py
python3 -m unittest discover -s tests/live-workbench -p 'test_*.py'
mvn -q -pl modules/live-workbench -am test
```

The checks prove pinned-source integrity and local core behavior only. They do
not represent 600 seconds of provider runtime, a production isolation audit, or
independent certification.
