
# Batch 46 runnable smoke packs

Every project ELMOS converts or generates ships with a runnable smoke pack. A
generated artifact that a recipient cannot start is not deliverable, regardless
of which other gates it passed.

- Repository-scoped Codex skills live in `.agents/skills/b46-*/SKILL.md`. Invoke
  the smallest relevant one explicitly with `$b46-...`.
- Attach a pack with `python3 scripts/batch46/scaffold_smoke_pack.py <project> --write`.
  It detects the stack, derives the minimal data needed to start, synthesizes
  disposable seeds, and emits the `script`, `compose`, `make` and `zero-dep`
  entries plus a vendored stdlib-only runner in `smoke/tools/`.
- Minimal means minimal: one row per table unless a declared constraint demands
  more, and no value for a column the schema does not require. A smoke pack that
  ships a test corpus has failed its own definition.
- Seed data comes only from `synthetic-from-contract` (default),
  `desensitized-sample` (requires an authorization reference and passes the
  sensitive-value scan) or `corpus-trim` (development corpora only — never
  holdout or representative workload corpora). Production data is never a source.
- Generated values are recognisably fake and primary keys come from the reserved
  range at or above 900,000,000, so a fixture row can never collide with an
  application row.
- Every run is a lease, not a deployment. The free quota is 10 minutes; expiry
  stops every started service, removes containers and volumes, and deletes all
  ephemeral smoke data. There is no auto-renew; extension requires explicit
  `--seconds`, `--reason` and `--actor`, and time beyond the free quota is
  recorded as `billable_seconds` for the Batch 44 metering boundary.
- Entries are honest. An entry that cannot be supported is emitted as
  `unavailable` with a reason. The zero-dependency entry exists only where an
  approved embedded substitute is declared and always carries its semantic
  warning; never swap a database engine the project does not declare support for
  in order to make a run go green.
- `NOT_RUN` never passes. A missing Docker daemon, absent toolchain or undeclared
  start command is recorded as `NOT_RUN` and blocks the gate.
- A passing smoke run means the artifact starts, answers once and stops cleanly.
  It is never evidence of route, framework, database, client, performance,
  security or accessibility quality, and no Batch 29-45 gate may cite it.
- If a project needs source edits to start, that is a generator defect. Fix the
  generator; do not patch around it inside `smoke/`.
- Run `python3 scripts/batch46/validate_smoke_pack.py <project>`; only
  `python3 scripts/batch46/run_smoke_gate.py <project>` may determine whether a
  project is `runnable`, `limited` or `blocked`, and only from a real executed
  run whose evidence digest still matches its content.
- Read `docs/batch46/IMPLEMENTATION_CONTRACT.md`, `QUALITY_GATES.md`,
  `MINIMAL_DATA_POLICY.md`, `RUNTIME_LEASE_POLICY.md` and `STACK_MATRIX.md`
  before changing any Batch 46 behaviour.
