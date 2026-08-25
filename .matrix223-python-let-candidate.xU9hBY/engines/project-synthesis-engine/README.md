# ELMOS Project Synthesis Engine

The engine turns a bounded natural-language project intent into an approved,
hash-bound requirement baseline and then generates independent Java, Python,
C#, TypeScript, Go, Kotlin, PHP, and Rust starter projects. Drafting does not
generate code; generation requires a reviewed approval artifact.

## Coding Agent model catalog

Unlike the Spring `rewrite-spring` long-tail repair step and cross-language
lowering (Batch 5) — both of which now have a real, in-process
`ModelEndpointProvisioning` call behind a disabled-by-default port (see
[ADR-0059](../../docs/adr/ADR-0059-coding-agent-model-catalog.md)) — this
engine has no runtime call to any model at all, by design: "Drafting does
not generate code; generation requires a reviewed approval artifact," and
every emitter under `src/elmos_project_synthesis/` is a deterministic
template, not an agent call. The "Coding Agent" for this business line is
the external drafting session (a human, or an agent such as the
`$elmos-project-synthesis` Skill) that turns natural language into the
approved, hash-bound `SynthesisRequest` *before* this engine ever runs —
that session can read `engines/ai-platform-engine/policies/model-catalog-v1.json`
directly like any other file; there is nothing for this Python package to
provision at generation time, and adding an in-process provisioning class
here would misrepresent this engine's architecture rather than describe it.

## Prerequisites

- Python 3.12–3.14
- `uv` 0.11.16 or a compatible locked runner
- the exact native toolchain for every target you intend to verify: Java 21,
  Python 3.12, .NET SDK 10.0.301, Node 26.0.0 with pnpm 10.12.4, Go 1.25.0,
  Kotlin 2.2.20 on JVM 21 with Gradle 8.14.3, PHP 8.4.12, or Rust 1.89.0

On Darwin arm64, the four non-default exact toolchains can be installed from
checksum-verified upstream distributions and immediately accepted with:

```bash
make project-synthesis-toolchains
```

The installer uses
`~/.local/share/elmos/toolchains` by default, never replaces a different
existing toolchain, and keeps Gradle 8.14.3 isolated from any newer Homebrew
Gradle. Override the absolute installation root with
`ELMOS_PROJECT_SYNTHESIS_TOOLCHAIN_ROOT` when required.

If the approved build environment requires an HTTP CONNECT proxy for Maven or
Gradle repositories, set `ELMOS_PROJECT_SYNTHESIS_GRADLE_PROXY` to an explicit
`http://host:port` or `https://host:port` URL before invoking `uv`. The verifier
converts that value to Gradle JVM properties. URLs containing credentials,
paths, queries, fragments, invalid hosts, or invalid ports fail closed; use a
local credential-free egress proxy instead of embedding secrets.

Kotlin verification also sets `GRADLE_USER_HOME` to the owner-only
`~/.cache/elmos/project-synthesis/gradle-user-home`, so ambient
`~/.gradle/init.d` scripts and repository rewrites cannot change the generated
build. Override it only with the absolute, non-symlink, owner-only
`ELMOS_PROJECT_SYNTHESIS_GRADLE_USER_HOME` directory.

```bash
cd engines/project-synthesis-engine
uv sync --locked
```

## 1. Create a reviewable draft

The Web Console `/generation` workspace also accepts a simple description,
UTF-8 TXT/Markdown, Word `.docx`, HTML, text-bearing PDF, exact repository
Skill names, and public HTTPS HTML. It extracts only reviewable text: imported
Skills are never executed, Word external-file access stays disabled, HTML
scripts/styles are discarded, scanned PDFs fail with an OCR-required status,
and URL fetching rejects credentials, private/loopback addresses, non-HTTPS
schemes, unsafe redirects, oversized responses, and non-HTML content.

Every imported source records its original byte digest, label, media type,
included/extracted character counts, truncation state, and warnings. The source
bundle is bound to the tenant, actor, combined description, and a canonical
SHA-256 digest before analysis. The approved request and generated
`requirements/source-provenance.json` preserve that binding; editing the
combined description invalidates the bundle and requires a new review.

The browser flow is:

1. Enter the project identity, tenant/actor-bound short-lived Runner token, and
   any simple description.
2. Add files, an optional public HTTPS page, and/or exact Skill names, then
   select **解析并合并来源**.
3. Review the merged description and every source/truncation warning; never
   treat extraction as requirements approval.
4. Select the exact language, persistence, and authentication tuple, then lock
   the generation plan.
5. Analyze the PSIR, resolve every open question, explicitly approve it, and
   select **一键生成、验证并归档**.
6. Download the digest-checked archive. Read `docs/LOCAL_RUN.md` for exact
   local software/hardware and startup steps, and `docs/CLOUD_DEPLOYMENT.md`
   plus `deploy/deployment-options.json` for cloud sizing, Cloud Run commands,
   rollback, cleanup, and still-`NOT_RUN` external gates.

```bash
uv run elmos-project-synthesis draft \
  --name order-service \
  --namespace io.elmos.orders \
  --description 'Create, list, and retrieve orders with a health endpoint.' \
  --entity order \
  --language java \
  --language python \
  --language typescript \
  --output synthesis-request.json
```

For the exact Python enterprise profile, select the production tuple explicitly:

```bash
uv run elmos-project-synthesis draft \
  --name order-service \
  --namespace io.elmos.orders \
  --description 'Create, list, and retrieve tenant-bound orders.' \
  --entity order \
  --language python \
  --persistence postgresql \
  --auth-mode jwt \
  --output synthesis-request.json
```

Replace `jwt` with `oidc` for the separately verified OIDC profile. Any other
production language, persistence, or authentication tuple is rejected instead
of being weakened to the in-memory starter.

The draft records requirements, acceptance criteria, assumptions, exact target
profiles, and open questions. Names, descriptions, namespaces, target profiles,
and ports are validated before the file is written.

For multi-entity natural-language intake, explicit markers take precedence over
fuzzy domain keywords. A single description can declare the complete starter
graph, for example:

```text
实体: product, inventory;
product字段: name:string:required, price:number:required;
inventory字段: product_id:string:required, quantity:integer:required;
关系: inventory.product_id -> product.id;
规则: inventory.quantity must be non-negative;
权限: admin:create/read/update/delete:inventory;
权限: viewer:read:product
```

An unparseable explicit relation or permission marker creates a blocking open
question; it is never silently replaced by a weaker interpretation.

## 2. Review and approve the baseline

Resolve every item in `open_questions` before approval. Approval binds the
reviewed payload to an actor, UTC-capable timestamp, and SHA-256 digest.

```bash
uv run elmos-project-synthesis approve \
  --request synthesis-request.json \
  --actor user:reviewer \
  --output approved-request.json
```

## 3. Generate into a new or engine-owned directory

```bash
uv run elmos-project-synthesis generate \
  --request approved-request.json \
  --output generated/order-service
```

The generator rejects broad output targets, non-empty unmanaged directories,
modified managed files, unsafe paths, invalid manifests, and a changed approved
baseline. Use a new output directory for a materially different approval.
Generated GitHub Actions references are pinned to immutable upstream commit
digests, and every non-`scratch` generated container base is pinned to an
official multi-architecture manifest SHA-256. Human-readable release labels
and image tags aid review but never determine immutable execution identity.

## 4. Run real target verification

```bash
uv run elmos-project-synthesis verify \
  --workspace generated/order-service \
  --evidence verification.json
```

Verification invokes only the selected native toolchains. A missing toolchain,
failed build, failed test, or failed startup probe returns a non-success result.
The optional runtime plan is also bound to the same exact toolchain selection;
it omits a target instead of falling back to a different version:

```bash
uv run elmos-project-synthesis runtime-plan \
  --workspace generated/order-service
```

The governed Web Console pipeline exposes a one-click runtime only for targets
whose real build, tests, and service-identity health probe passed. Production
mode uses a rootless container engine, per-job internal-only networking,
loopback publication, a read-only filesystem, dropped capabilities,
`no-new-privileges`, and CPU/memory/PID limits. Host execution is an explicit
development-only profile and is rejected when `NODE_ENV=production`.
After a browser refresh, an operator can recover an atomically persisted task by
its complete UUID, tenant, actor, and a re-entered short-lived token. The token
is not written to browser storage, and a tenant/actor mismatch fails closed.

## Generated structure and equivalence views

Every generated archive carries one digest-bound, machine-readable insight bundle
and its human-readable chart projection:

- `requirements/project-structure.json` inventories the repository, shared
  operational roots, every selected application, and its source, test, build,
  configuration, API, and container areas. Its coverage denominator is every
  manifest-managed generated file; an unknown root or dangling edge blocks
  verification before a native command runs.
- `requirements/declared-dependency-graph.json` records direct runtime,
  framework, build-tool, and provider declarations. Native transitive resolution
  initially remains `NOT_RUN` and `complete=false`; this graph is not presented
  as a resolved SBOM.
- `requirements/project-insights.json` combines those graphs with approved-input
  semantic traceability, per-target exact-toolchain/build/startup evidence, a
  complete selected-target pair matrix, and separate completion denominators.
- `docs/PROJECT_INSIGHTS.md` renders deterministic Mermaid structure and
  dependency diagrams plus semantic, behavioral, and completion tables. The Web
  Console renders the same allowlisted data as accessible React/CSS charts; it
  never executes generated Mermaid or HTML.

For greenfield generation, hash-bound requirement-to-PSIR-to-artifact mapping can
pass while direct source/target semantic equivalence remains `NOT_RUN`: there is
no executable pre-conversion source program. Likewise, independently passing all
selected targets does not prove pairwise behavioral equivalence. Every
off-diagonal pair remains `NOT_RUN` until both exact targets run the same governed
behavior corpus and their normalized observations are compared. Structure,
traceability, native target verification, direct semantic equivalence, direct
behavior equivalence, independent verification, and certification are therefore
shown separately and are never averaged into one misleading score.

## Evidence boundary

All eight emitters accept the exact `api` + `in-memory` + `auth=none` starter
and the exact PostgreSQL 17.5 + JWT/OIDC production profile. The production
profile emits executable default-deny authorization,
tenant-bound queries plus forced PostgreSQL RLS, forward migrations, file-based
Secret references, Prometheus metrics, structured request logs, Kubernetes
security/network policy, SLO definitions, and backup/restore runbooks.
Java and Python accept multi-entity production requests; Go, TypeScript, C#,
Kotlin, PHP, and Rust currently enforce an explicit single-entity production
boundary. Uncompiled rules, ambiguous production relations, multi-entity
requests outside that exact boundary, and every unsupported profile/target
tuple fail closed.

The portable starter acceptance executes every exact toolchain available on the
current host and preserves unavailable targets as `NOT_RUN`:

```bash
uv run python scripts/run_acceptance.py
```

Use `--require-all-toolchains` when the environment is expected to contain the
complete eight-target matrix; then any unavailable exact toolchain returns
non-zero. A failed build always returns non-zero in both modes.

Python verification stores a content-addressed `uv.lock` under
`~/.cache/elmos/project-synthesis/locks` after the first successful resolution,
then restores it with owner-only permissions and validates it with
`uv lock --check`. Set `ELMOS_PROJECT_SYNTHESIS_LOCK_CACHE` to an absolute
private cache directory when a controlled runner needs a different location.
The cache makes repeated identical generation resilient to transient index
failures; the first unseen `pyproject.toml` still requires a pre-warmed cache or
authorized package-index access, so this is not a claim of arbitrary offline
execution.

Every local production-profile path is replayable separately, or as the full
16-case matrix:

```bash
uv run python scripts/run_production_acceptance.py --language java --auth-mode jwt
uv run python scripts/run_production_acceptance.py --language rust --auth-mode oidc
uv run python scripts/run_production_matrix.py
```

Each command generates a fresh managed workspace and requires the exact local
Python and PostgreSQL toolchains. It applies forward migrations, starts the
database and API, creates only ephemeral local identity material, and runs the
tenant-isolation CRUD test. A successful local result does not change
`production_delivery_status` or `external_certification_status`; both remain
`NOT_RUN`.

Generated assets and local execution are engineering evidence. Image approval,
real provider provisioning, production migration/deployment, alert delivery,
restore/DR exercises, assistive-technology review, independent user acceptance,
external assessment and certification remain `NOT_RUN` / `NOT_CERTIFIED` until
their authorized independent evidence exists.
