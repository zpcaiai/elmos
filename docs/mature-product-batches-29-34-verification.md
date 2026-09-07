# Mature product Skills Batches 29–34 verification

## Outcome

The repository now contains the complete installable Batch 29–34 mature-product Skill series described in `ChatGPT-跨语言迁移月报 (1).md`. This is additive to the existing ELMOS execution engines: the established Batch 22–26 engine numbering and Flyway V28–V32 history were not renamed, replaced, or reinterpreted.

| Batch | Scope | Skill IDs | Skills | Schemas | Toolkit tests |
|---|---|---:|---:|---:|---:|
| 29 | Directed language-route certification | 1141–1160 | 20 | 3 | 3 |
| 30 | Framework and version migration packs | 1161–1180 | 20 | 4 | 3 |
| 31 | Database and data-platform modernization | 1181–1202 | 22 | 6 | 5 |
| 32 | Frontend, desktop, and mobile modernization | 1203–1222 | 20 | 7 | 6 |
| 33 | Cloud, IaC, and DevOps modernization | 1223–1242 | 20 | 8 | 7 |
| 34 | Ultra-large repository and portfolio scale | 1243–1264 | 22 | 10 | 7 |
| **Total** |  | **1141–1264** | **124** | **38** | **31** |

The installation also includes 52 JSON templates, 38 deterministic Python tools, the six documentation sets, six Makefile entry points, repository-level Agent instructions, and an aggregate verifier.

## Verification performed on 2026-07-22

- The standalone Batch 34 ZIP and cumulative Batch 29–34 ZIP passed archive integrity checks and matched their declared SHA-256 values.
- All 31 toolkit tests passed after installation. Negative cases confirmed that missing evidence cannot be converted into `certified` merely by editing a status field; unknown graph references, unsafe unattended cloud commands, and unknown portfolio work-unit repositories are rejected.
- All 124 repository Skills passed the official Skill Creator `quick_validate.py` check. The source archive contained one unquoted colon in `b29-route-economics-certifier`; the installed copy quotes the YAML description and now passes.
- The aggregate validator confirmed six complete batches, unique Skill names, contiguous IDs 1141–1264, required operating sections, valid local references, 38 meta-valid Draft JSON Schemas, and 52 parseable JSON templates.
- `make mature-product-skills` is the reproducible repository command for the six validators, 31 tests, and aggregate audit.

Source and installed-payload digests are recorded in `docs/mature-product-batches-29-34-source-manifest.json`.

## Evidence boundary

This result proves the Skill packages, typed contracts, templates, scaffolders, validators, conservative gates, negative tests, and repository integration. It does **not** certify a concrete Java-to-C# route, framework migration, production database conversion, browser/device migration, cloud deployment, million-line monorepo, thousand-repository campaign, Runner Fleet, or disaster-recovery exercise.

Those field claims remain `NOT_RUN` until an exact source/target tuple, authorized owners, real toolchains, isolated runtime, holdout corpus, representative workloads, cost evidence, rollback/cleanup evidence, and the applicable batch gate are supplied. No external provider operation, source mutation, PR creation, cloud apply, production data write, or fleet execution occurred during this verification.

## Installed locations

- Skills: `.agents/skills/b29-*` through `.agents/skills/b34-*`
- Shared contracts: `docs/batch29` through `docs/batch34`
- Schemas and templates: `schemas/batch29` through `schemas/batch34`, and `templates/batch29` through `templates/batch34`
- Tooling and tests: `scripts/batch29` through `scripts/batch34`, and `tests/batch29` through `tests/batch34`
- Aggregate audit: `scripts/validate_mature_product_series.py`
