# Mature product Skills Batches 29–45 verification

## Completion result

The complete mature-product blueprint from the supplied monthly report is installed as repository-scoped Codex Skills. Skills 1141–1496 are contiguous and unique across Batches 29–45.

| Series | Batches | Skill IDs | Skills | Schemas | Templates | Toolkit tests |
|---|---:|---:|---:|---:|---:|---:|
| Imported and normalized | 29–34 | 1141–1264 | 124 | 38 | 52 | 34 |
| Exact Batch 35–37 packages plus generated Batches 38–45 | 35–45 | 1265–1496 plus B37-X01–X16 | 248 | 82 | 90 | 71 |
| **Total** | **29–45** | **1141–1496 plus B37-X01–X16** | **372** | **120** | **142** | **105** |

Batch 35 comes from the supplied `batch35-codex-skills` package whose 78-entry file manifest was checked with zero missing files. Batch 36 comes from the supplied `batch36-codex-skills` package whose 83-entry file manifest was checked with zero missing files. Batch 37 comes from the supplied complete package, but its 624-entry manifest is stale: the directory has 668 non-cache files, omits 73 non-cache paths, and lists 29 absent cache paths. Actual Batch 37 files were therefore audited directly; details are in `docs/batch37/IMPORT_AUDIT.md`. Batches 38–45 remain reproducibly generated from the monthly-report authority. Every Batch 35–45 Skill includes `agents/openai.yaml`; all 248 Skills in that range and all 124 imported Batch 29–34 Skills pass the repository validators.

## Implemented assets

- `.agents/skills/b29-*` through `.agents/skills/b45-*`
- `docs/batch29` through `docs/batch45`, including the exact Batch 35–45 authority sections
- `schemas/batch29` through `schemas/batch45`
- `templates/batch29` through `templates/batch45`
- Batch 29–37 exact deterministic tools plus the shared `scripts/mature_product_toolkit.py` for Batches 38–45
- Batch-specific Make targets and the aggregate `make mature-product-skills` entry point
- Reproducible Batch 38–45 compatibility generator at `skills/generate_mature_product_batches_35_45.py`; it explicitly excludes Batches 35–37 so it cannot overwrite any richer authority package
- Source and payload digests in the two mature-product source manifests
- Deterministic standalone and cumulative ZIPs under `artifacts/mature-product-skills`, each with an adjacent archive SHA-256 file and an internal per-file SHA-256 manifest

## Verified behavior

- Batch 29–34 toolkit tests: 34/34 pass.
- Batch 35 toolkit tests: 9/9 pass; Batch 36 toolkit tests: 9/9 pass; Batch 37 toolkit tests: 21/21 pass; Batches 38–45 toolkit tests: 32/32 pass.
- Aggregate structural audit: 17 batches, 372 Skills, 120 meta-valid Schemas, and 142 parseable templates pass.
- Negative gates reject status-only `CERTIFIED`, empty evidence, failed or missing holdout and representative results, critical findings, missing batch metrics, and external operations without authorization references.
- Generator compatibility covers the 172 Batch 38–45 definitions while Batches 35–37 remain protected from generic regeneration.
- Both distribution ZIPs rebuild byte-for-byte deterministically, pass `unzip -t`, and pass every internal file-manifest checksum.
- Full architecture verification passes 58/58 tests after installing the final source manifests, Batch 36–37 runtime boundaries, and count baselines.
- `modules/advanced-verification` executes 14/14 Java tests in the local Java 21 rehearsal; the generated pack passes structural validation with the explicit decision `NOT_CERTIFIED`.
- `modules/developer-workflow` executes 18/18 Java tests and real local CLI `inspect`/`preview` replay; the generated Developer Experience Pack passes structural validation with the explicit decision `NOT_CERTIFIED`.
- `modules/extension-marketplace` executes 24/24 Java tests, including real SHA-256 and Ed25519 verification, default-deny sandboxing, tenant isolation, exact dependency/release state, revocation, offline rights, decimal settlement conservation, and EOL controls. Its local Marketplace Pack passes both structural gates with `NOT_CERTIFIED` and `closure_complete=false`.
- The full Java 21 Maven reactor reports 917 tests, 0 failures, 0 errors, and 1 pre-existing Docker-dependent skip. Cross-stack regressions also pass: .NET 12/12, Python 31/31 plus Ruff and mypy, frontend 34/34, and the web-console production build.

## Evidence boundary

This completion proves installable Skills, procedural contracts, Schemas, templates, scaffolders, validators, negative gates, tests, and repository integration. It does not prove that every language route, framework, database, client, cloud, portfolio, formal solver, IDE plugin, Marketplace, deployment edition, global SRE environment, supply-chain certification, knowledge model, Agent workforce, LTS upgrade, economic model, or customer outcome has run in production.

All such field claims remain `NOT_RUN` until the exact source/target or product tuple has authorized owners, real toolchains and environments, independent holdout and representative workloads, raw evidence and provenance, cost and risk evidence, rollback or recovery evidence, and the applicable conservative gate. No source mutation, PR publication, production data write, cloud Apply, customer communication, fleet execution, certification issuance, or external operation was performed by this packaging task.
