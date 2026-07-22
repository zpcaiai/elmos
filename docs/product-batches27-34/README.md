# ELMOS Product Batches 27-34 and Migration Packs M29-M34

## Namespace boundary

Two independent specifications use overlapping numbers. This repository makes the distinction explicit:

| Namespace | Scope | Decision authority |
|---|---|---|
| Product Batch 27-34 | TBM, workforce, transformation, control tower, MVP engineering/audit, secure Java vertical loop, enterprise IAM | `ProductRoadmapGovernance`, followed by a named human |
| Migration Pack M29-M34 | directed language route, framework, database, client, cloud/IaC and portfolio-scale certification | the exact `scripts/batchXX/run_*_gate.py` |

Product code and APIs must never call a Migration Pack `Batch 29` without the `M29` namespace.

## Product implementation

- `modules/product-roadmap-governance` contains the exact B27-B34 catalog, sequential fail-closed gates and domain-specific B27-B30 controls.
- B27 rejects unreconciled cost, allocation gaps, late benefit baselines, double counting and unbound capitalization/chargeback policy.
- B28 rejects personal ranking, opaque attrition prediction, automated employment decisions, invasive individual telemetry, missing consent and missing appeals.
- B29 rejects portfolio dependency gaps, change-capacity saturation, self-reported-only adoption, late/double-counted benefits and cutover without rollback.
- B30 requires identity/provenance, temporal truth, bounded plans, policy allow, idempotency, compensation, kill switch and separation of duties; autonomous production execution is forbidden.
- B31 and B33 reuse the existing immutable snapshot, secure Runner, deterministic Rewrite, independent validation, Temporal, PR and Evidence modules.
- B32 is an independent gap-review status. Historical scaffold claims are not imported as current evidence.
- B34 reuses `modules/enterprise-governance` for verified tenant context, OIDC/SAML boundaries, RBAC/ABAC, RLS, workload identity, secret lease, JIT/break-glass constraints, audit and data governance.

Control-plane APIs:

```text
GET  /api/v1/product-roadmap/capabilities
POST /api/v1/product-roadmap/batches/{batch}/evaluate
POST /api/v1/product-roadmap/batches/27/tbm/evaluate
POST /api/v1/product-roadmap/batches/28/workforce/evaluate
POST /api/v1/product-roadmap/batches/29/transformation/evaluate
POST /api/v1/product-roadmap/batches/30/control-tower/evaluate
```

The batch evaluator returns only `BLOCKED` or `READY_FOR_HUMAN_DECISION`; the domain controls return only `BLOCKED` or `READY_FOR_HUMAN_REVIEW`. Neither grants approval or executes external work.

## Migration Pack implementation

The repository package contains 124 repository Skills, 38 Draft JSON Schemas, 52 JSON templates, 38 deterministic Python tools and 31 toolkit tests. The same 124 Skills are also installed in `agent-skills/runtime` with valid OpenAI interface metadata.

`modules/migration-pack-certification` validates tenant, exact source/target snapshots, pack version, independent judge, real environment, default-deny networking, idempotency, semantic integrity, unsupported counts, risk and immutable evidence. Its API is admission-only:

```text
GET  /api/v1/migration-pack-certification/capabilities
POST /api/v1/migration-pack-certification/M{pack}/admission/evaluate
```

It returns `READY_FOR_PACK_GATE` or `BLOCKED` and always returns `certified=false`. Only the exact pack script can evaluate certification readiness.

## Persistence and Skills

Flyway V33-V40 adds 664 tenant-scoped, forced-RLS, append-only product evidence projections. V41 adds six Migration Pack admission/gate-receipt projections. No migration stores secret values or authorizes external execution.

The commercial source contributed 165 unique Runtime Skills: B27 18, B28 18, B29 18, B30 18, B31 18, B33 35 and B34 40. B32 is an audit/result section and contains no Skill frontmatter. Combined with the 124 Migration Pack Skills, this work installs 289 new Runtime Skills; the repository total is 615. Source names exceeding the official 64-character limit use deterministic hashed aliases recorded in `skill-source-manifest.json`.

## Evidence boundary

Repository validation proves contracts, negative controls, schemas, deterministic toolkit behavior, module compilation and local tests. It does not prove real finance/HR outcomes, customer migrations, route/framework/database/client/cloud certification, private repository access, browser/device behavior, production infrastructure, portfolio scale, IdP integration, Runner isolation or disaster recovery. Those outcomes remain `NOT_RUN` until the exact external authorities and environments produce immutable evidence.
