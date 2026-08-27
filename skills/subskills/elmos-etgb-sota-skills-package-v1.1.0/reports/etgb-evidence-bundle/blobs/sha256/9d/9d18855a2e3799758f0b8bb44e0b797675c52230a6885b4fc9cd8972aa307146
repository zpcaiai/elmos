# Elmos ETGB v1.1.0 Validation Summary

Validation date: 2026-08-27

## Delivered scope

- Skills: **24**; dependency graph valid, no missing Skill and no cycle.
- Concrete cases: **46,664**.
- Declared capability IDs: **794** — 694 domain capabilities plus 100 cross-cutting production capabilities.
- Cross-cutting concrete cases: **800** (`4 business lines × 100 scenarios × 2 fault positions`).
- Priority distribution: P0 7,204; P1 31,530; P2 7,930.

| Domain | Cases | Capability IDs |
|---|---:|---:|
| Spring modernization | 3,117 | 222 |
| Repository cross-language conversion | 29,535 | 174 |
| Multilingual project generation | 1,451 | 91 |
| SQL dialect/routine conversion | 11,761 | 207 |
| Cross-cutting production quality | 800 | 100 |

## Executed checks

| Check | Result |
|---|---|
| Python compile check | PASS |
| Package/schema/ID validation | PASS — 46,664 cases |
| Declared matrix coverage | PASS — missing 0, unexpected 0 |
| Mandatory assurance techniques | PASS — 8/8 |
| Skills manifest/frontmatter/dependencies | PASS — 24/24 |
| Unit and reference integration tests | PASS — 26/26 |
| Offline domain smoke | PASS — 4/4 |
| Smoke weighted pass rate | 100% |
| Smoke P0 critical Oracle pass rate | 100% |
| Smoke SSER | 0% |
| Smoke evidence completeness | 100% |
| Reference evidence bundle | PASS — sealed, HMAC signature valid |
| Authority positive/negative examples | PASS — allowed request granted; out-of-root request denied |
| Candidate freeze and digest | PASS |
| Risk plan, stable shards and machine ETA example | PASS |

The smoke-only gate intentionally returns **REJECT/BLOCKED**, not promotion: 17 public corpus entries still require legal/license approval and a four-case smoke run has no P1/P2 release evidence. This demonstrates fail-closed certification rather than a false release claim.

## Intentional release blockers

`etgb validate --release` returns exit code 2 because all 17 public corpus records remain `license_review: required`. This is intentional. A repository commit pin is not a legal approval; Elmos must record the actual license decision before commercial release execution.

## Environment limitations

Only the four completely offline smoke fixtures and the 26 local unit/reference integration tests were executed here. The following were **not** claimed as executed:

- 46,660 external/container/database-backed cases;
- live Oracle, SQL Server, DB2, Snowflake, BigQuery or Kubernetes runs;
- public repository builds requiring network fetches;
- 500k/1M LOC Golden Route runs;
- PostgreSQL migration/RLS execution against a live PostgreSQL server;
- performance, soak, multi-seed and fault campaigns on a production benchmark cluster.

Those cases are fully materialized and carry Adapter/Oracle/profile requirements, but become executable only after Elmos connects `integrations/harness/adapter-contract.yaml` to its production workers, sandboxes, databases and provider infrastructure.

## Release interpretation

The package itself is structurally and locally valid. It is **not a certified Elmos product release**. Product certification requires a frozen real candidate, approved corpus licenses, complete release/golden execution, all mandatory seeds, sealed evidence, and every non-waivable gate passing.
