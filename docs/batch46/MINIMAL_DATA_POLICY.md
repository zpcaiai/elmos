# Batch 46 — Minimal data policy

## What "minimal" means

The smallest set of environment values, rows and stub upstreams without which
the process cannot reach a ready state or serve one functional request.

Concretely:

- one row per table, unless a declared constraint requires more;
- a value for a column only where the schema demands one — `NOT NULL` without a
  default, a primary key, a unique key, or a foreign key parent;
- no value for a nullable column with no constraint, even when it would look
  nicer populated;
- environment variables only where the project's own contract declares them.

A smoke pack that ships enough data to demo the product has stopped being a
smoke pack. Demo data, test corpora and holdout corpora are different artifacts
with different owners.

## Permitted data sources

Exactly three, recorded per artifact in `smoke/seed-manifest.json`.

### 1. `synthetic-from-contract` — the default

Derived only from artifacts the project already contains: SQL DDL, migrations,
OpenAPI/proto contracts, `.env` templates, framework configuration. Deterministic
from a seed, so the same pack yields the same rows.

Every generated value is recognisable on sight:

| Shape | Example |
| --- | --- |
| string | `SMOKE-8C87EAF2A1` |
| email | `smoke-7fab7b18@smoke.invalid` |
| secret | `smoke-local-only-dc2aebe2c6956842` |
| primary key | `900006024` (reserved range ≥ 900,000,000) |
| timestamp | `2000-01-01 00:00:00` |

Reserved-range keys mean a fixture row cannot collide with a row the application
creates while it runs. Explicit keys do not advance identity sequences — which is
acceptable in a throwaway database and unacceptable anywhere else.

### 2. `desensitized-sample` — opt-in, authorized, scanned

Permitted only with `--sample-authorization <reference>`: the approval that
permits reuse of that sample. The synthesizer then scans the file for
email-shaped, card-shaped, national-ID-shaped, bearer-token-shaped and private-key
values and **refuses by default** when it finds any. Overriding requires
`--accept-scan-findings`, and the findings are written into the manifest where a
reviewer will see them.

The scan is a backstop against mistakes, not a desensitization tool. A file that
needs the override probably was not desensitized.

### 3. `corpus-trim` — development corpora only

A trimmed slice of an existing **development** corpus. Holdout and
representative-workload corpora are never touched: reusing them here would
contaminate the independence that Batches 29-34 depend on, and it would do so
invisibly.

## Never permitted

Production data. No anonymization argument, no "it's only one row", no "the
customer sent it to us". `seed-manifest.json` carries
`production_data_used: false`; the gate fails immediately if it is ever true.

## Secrets

Variables whose names look like credentials get freshly generated throwaway
values — never the contract's placeholder, never a real credential, never a value
reused across projects. They are local-only by construction and are not written
to any deployed configuration.

## Connection strings

A DSN copied from `.env.example` points at whatever the author had locally, so it
is not carried into the run. `smoke/seed/runtime-overrides.json` supplies the
value per entry: the compose topology's DSN for `compose`, the ephemeral SQLite
path for `zero-dep`, and nothing at all for `script` — which deliberately runs
against whatever the operator already has.

## Classification and lifetime

Every artifact is classified `ephemeral-disposable`. The seed files live in the
pack; the data they create lives only inside the runtime lease. `smoke/README.md`
tells the recipient, in their own language, not to load any of it into a shared
or production database.
