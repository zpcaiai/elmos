# Elmos ETGB Full-Product Assurance Skills Package v2.0.0

**ETGB — Elmos Enterprise Test, Transformation & Generation Benchmark** is the unified test operating system and release-certification contract for the complete declared Elmos product surface.

It retains the four repository-engineering business lines and adds platform, AI runtime, Agent protocol, RAG, project intelligence, online IDE/debug, collaboration, billing/payment, APIs, storage, deployment, security/compliance, UI/accessibility, analytics/admin, notification, AI-solution generation, data platform and commercial delivery testing.

## Delivered scope

- **75,419 materialized executable test specifications**;
- **1,452 governed product features** across **23 product domains**;
- **23,232 exact feature-to-case bindings** with 100% declared coverage;
- **41 end-to-end journeys × 5 personas × 3 variants = 615 cases**;
- **100 controls across 11 engineering-assurance profiles × 3 evidence surfaces = 300 cases**;
- **5,400 cross-cutting fault/security/recovery cases** across 27 core/product domains;
- **50 composable Skills**;
- **25 production Adapter contracts** for full-product domains, journeys and standards;
- **12 fully offline smoke cases**, including the original four engineering lines and eight critical product-control examples.

> “Full product” means every feature declared in `matrices/feature-registry.yaml` plus the four transformation/generation business lines. It is deliberately extensible and does not claim mathematical coverage of future or undeclared functionality.

## Coverage domains

| Domain | Capabilities | Materialized cases |
|---|---:|---:|
| Spring modernization | 222 | 3,117 |
| Whole-repository cross-language conversion | 174 | 29,535 |
| Multilingual project generation | 91 | 1,451 |
| SQL dialect/routine conversion | 207 | 11,761 |
| Full product feature domains | 1,452 | 23,232 + 8 smoke |
| Cross-domain journeys | 41 | 615 |
| Engineering assurance controls | 100 | 300 |
| Cross-cutting production scenarios | 100 | 5,400 |

## Package layout

```text
skills/          50 production test/assurance Skills
matrices/        feature registry, 23 domains, journeys, standards and fault matrices
suites/          75,419 concrete JSONL cases and machine-readable index
schemas/         case, plan, feature, journey, adapter, evidence and runtime schemas
etgb/            CLI, materializer, feature coverage, Oracles, planning, scoring and gates
integrations/    PostgreSQL/RLS, Harness Adapter catalog, OpenAPI, AsyncAPI, OTel and policy
fixtures/        original and full-product offline smoke systems
corpora/         pinned public repository metadata and license review status
docs/            full-product plan, coverage model, implementation status and runbooks
```

## Verify

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
make verify
```

The principal commands are:

```bash
etgb materialize
etgb validate
etgb skills-audit
etgb coverage
etgb feature-coverage --output reports/FEATURE_COVERAGE.json
etgb run --profile smoke --output reports/smoke-results.jsonl
etgb score reports/smoke-results.jsonl --output reports/smoke-score.json
pytest -q
```

## Production truth boundary

The package fully materializes test specifications and reference control-plane behavior. The 25 external product adapters and the existing repository/database adapters must still be implemented against Elmos workers, browsers, model providers, databases, payment sandboxes, Kubernetes and observability infrastructure before all external cases become executable.

Release profiles are prohibited from using `--allow-unavailable`; an unavailable Adapter, hidden-test authority violation, unexplained financial delta, cross-tenant leak, data corruption, privilege expansion, P0 silent semantic error or incomplete evidence blocks promotion.

Read `docs/FULL_PRODUCT_TEST_PLAN.md`, `docs/FUNCTION_INVENTORY.md`, `docs/FEATURE_COVERAGE_MODEL.md`, `docs/ADAPTER_IMPLEMENTATION_STATUS.md`, `docs/STANDARDS_MAPPING.md` and `skills/manifest.yaml` first.
