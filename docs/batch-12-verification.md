# Batch 12 verification: Python Legacy Modernization Engine

Verified on 2026-07-21 in the local macOS workspace. This document separates repository-complete behavior from evidence that can only be produced by an approved Linux, GPU, Windows, Notebook, private-index, data, or model Runner.

## Repository-complete scope

- `engines/python-engine` is an independently deployable Python 3.14 FastAPI Worker implementing the shared capability, scan, plan, execute-step, validate, job lookup, and cancellation routes.
- Static intake discovers project roots, monorepos, version sources, dependency managers, indexes with credential redaction, frameworks, entry points, notebooks, system dependencies, and version conflicts without executing customer code.
- Environment analysis distinguishes five reproducibility states and supports uv, pip-compatible, Poetry, Conda, `uv.lock`, `pylock.toml`, Poetry, Pipenv, Conda, and hashed requirements contracts. It never calls a package resolver during static scan.
- Semantic analysis uses LibCST metadata and CPython AST 3.14 separately, emits source-qualified symbols and confidence-bearing edges, skips generated files, records parse gaps, and leaves mypy, Pyright, and runtime observations explicitly `NOT_RUN_REQUIRES_SANDBOX`.
- Planning creates distinct Web, Data Pipeline, and AI/ML profiles and acceptance gates from a versioned compatibility snapshot. Python 3.15 is excluded from production targets.
- Python 2 risk inventory keeps `2to3` candidate-only, identifies bytes/text, integer division, comparison, import, pickle, and compatibility-layer risks, and requires Golden Behavior evidence.
- Packaging analysis identifies legacy setup execution, native sources, NumPy C-API breaks, target-wheel gaps, source-build isolation, artifact hashes, and a Python/ABI/OS/architecture/libc/CUDA wheel matrix.
- Django and Flask advisors preserve incremental upgrade and WSGI/ASGI boundaries. Unsupported Django plugins are blockers; Flask context risk never triggers an automatic framework replacement.
- Notebook/pipeline analysis emits cell dependencies, hidden-state and side-effect findings, data-contract requirements, and explicit Runner-only clean-kernel status.
- Model scanning hashes but never loads executable artifacts. TensorFlow 1 uses staged candidate conversion; feature, GPU, artifact-environment, load-matrix, inference, and training evidence remain separate.
- Numerical validation exposes dtype, shape, null/schema, metric tolerance, optional ULP, randomness, ordering, and business-invariant failures. Model validation fails on missing load-matrix, signature, threshold, training, test-identity, or hardware-separation evidence.
- Java routes `PYTHON` as the third engine and combines Java, .NET, Python Web/Data/Model plans through HTTP, message, data, model, shared-database, file, and package edges without crossing tenants.
- Flyway V12 adds 71 Python analysis/evidence tables with forced row-level tenant isolation; five new evidence tables are append-only.
- P001-P014 have validated `SKILL.md` files and `agents/openai.yaml` metadata. P001's three adversarial cases are stored as prompt-only evaluations; they are not represented as executed model assertions.

## Verification evidence

| Check | Result |
| --- | --- |
| Python 3.14 `pytest -q` | 31 passed |
| Ruff | passed |
| mypy over 19 source files | passed with no issues |
| HTTP Worker | scan succeeded with 9 content-addressed evidence references; same-key replay stable; same-key/different-input blocked |
| HTTP tenant boundary | owner lookup 200; cross-tenant lookup 404; terminal cancellation 409 |
| JSON Schema | five metaschemas and five emitted payload classes passed Draft 2020-12 validation |
| P001-P014 | all 14 passed `quick_validate.py`; all 14 agent manifests parsed |
| Maven reactor | 39 reactor projects succeeded; 184 tests, 0 failures, 0 errors, 1 Docker-dependent skip |
| Java architecture | 17 tests passed, including Python/.NET engine boundary rules |
| .NET regression | 11 tests passed; `dotnet format --verify-no-changes` passed |
| Web Console | TypeScript check and Next.js 16.2.10 production build passed |
| PostgreSQL 17 V1-V12 | 523 tables, 522 RLS policies, 523 tenant columns, 13 total append-only triggers |
| PostgreSQL RLS | `org-a` saw only `python-a`; missing tenant context saw 0 rows |
| PostgreSQL append-only | update to `python_environment_snapshots` rejected by trigger |
| Skill inventory | 35 Build Skills and 87 Runtime Skills |
| Runner manifest | 5 Python profiles, immutable base-image digests, all `NOT_BUILT` and `UNAPPROVED` |

The disposable PostgreSQL cluster was stopped and moved to `/Users/stephen/.Trash/elmos-b12-pg.atAPDx-20260721065951`; it is recoverable. The workspace is not a Git repository, so no commit or remote CI claim exists.

## Batch 12 acceptance scenarios

All 18 scenarios have a versioned expectation in `engines/python-engine/test-fixtures/batch12-acceptance-scenarios.json`. Repository tests exercise the deterministic decision boundary for unpinned requirements, version conflicts, Python 2 semantics, candidate-only `2to3`, LibCST fixpoint behavior, Django staging/plugin blockers, Flask context, notebook state, dtype/randomness, native ABI, TensorFlow staging, hardware separation, executable artifact quarantine, disappearing tests, GPU routing, and the unified portfolio.

These tests prove routing, analysis, transformation, schema, and fail-closed decisions. They do not prove that an arbitrary customer application, dataset, native extension, or model has migrated successfully.

## External evidence gates

The following remain `NOT_RUN`, `NOT_BUILT`, or `UNAPPROVED` until the corresponding infrastructure and customer assets are authorized:

1. Build, scan, attest, and approve the five digest-pinned Runner images. The local Docker client exists, but its OrbStack daemon was not running.
2. Reproduce a real Python 2/old-glibc baseline, capture installed distributions and hashes, and compare Golden Behavior in the isolated Legacy Runner.
3. Resolve private indexes and native wheels with short-lived credentials, approved egress, dependency-confusion policy, offline replay, SBOM, and license evidence.
4. Run mypy/Pyright and bounded runtime tracing against representative customer tests; runtime traces may only describe executed paths.
5. Execute each Django feature-version stage and Flask HTTP/session/deployment contract against real services and databases.
6. Restart and run real notebooks in a clean kernel; verify schedules, retries, backfills, idempotency, partial failure, and side effects against approved test systems.
7. Build and execute CUDA/GPU and Windows matrices, recording driver, CUDA, cuDNN, wheel, device, precision, and determinism evidence.
8. Load pickle/joblib/checkpoint artifacts only in an origin-verified, no-network, no-secret, resource-limited sandbox; complete original/target/compatibility load matrices.
9. Run customer-approved numerical, data, inference, training, shadow-serving, performance, and business-invariant comparisons. `INCONCLUSIVE` cannot become `PASS`.
10. Exercise real SCM PR/MR, Checks, Evidence Pack, attestation, billing/audit, rollback, and cross-language cutover paths under tenant authorization.

Batch 12 is therefore complete at the repository implementation and fail-closed contract level. Production or customer-migration readiness remains evidence-gated per item above.
