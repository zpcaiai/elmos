# Company-series Batches 15–18 verification

Verification date: 2026-07-22.

## Repository result

| Surface | Result |
| --- | --- |
| Authoritative Skills | 285 packages initialized with Skill Creator; 285/285 pass `quick_validate.py` in an isolated `uv + PyYAML` runtime |
| UI metadata | 285/285 quoted `agents/openai.yaml` files parse and reference their `$skill-name` |
| Source integrity | Four manifests pin exact ranges, counts and SHA-256 authority-text digests |
| Contracts | 16 strict Draft 2020-12 schemas parse; local references resolve |
| Control plane | 6/6 evaluator and artifact tests pass; four program definitions remain read/evaluate/write-artifact only |
| Architecture and persistence | Company-series architecture 4/4 and migration contract 1/1 pass; the current global architecture re-run also passes after all expected verification files were installed |
| Persistence contract | V24–V27 declare 255 dedicated-schema tables, forced RLS and 42 append-only evidence streams |
| PostgreSQL 17.5 | V1–V32 applied in order; 255/255 company-series tables have forced RLS and `tenant_isolation`; all 42 append-only triggers exist |
| Tenant and immutability probes | A non-owner scoped to `org-company-a` saw one of two rows; update of `company_ops.decision_logs` was blocked |
| Field acceptance | 285/285 rows are `NOT_RUN`; no final company, AI, vertical or group-integration status is claimed |
| Full Java reactor | The current 61-child-module reactor completes with exit code 0; 134 Surefire reports contain 830 tests, 0 failures, 0 errors and 1 environment-dependent skip |

## Commands

```bash
uv run --with pyyaml python /Users/stephen/.codex/skills/.system/skill-creator/scripts/quick_validate.py <skill-directory>
jq empty contracts/{company-operating-system-schema,agent-workforce-schema,vertical-solution-schema,group-integration-schema}/*.schema.json
JAVA_HOME=/opt/homebrew/Cellar/openjdk@21/21.0.11/libexec/openjdk.jdk/Contents/Home /opt/homebrew/Cellar/maven/3.9.10/bin/mvn -pl modules/company-series -am test
JAVA_HOME=/opt/homebrew/Cellar/openjdk@21/21.0.11/libexec/openjdk.jdk/Contents/Home /opt/homebrew/Cellar/maven/3.9.10/bin/mvn test
```

The fresh PostgreSQL 17.5 instance applied all current V1–V32 migrations. `company_ops` contained 88 tables, `agent_workforce` 76, `vertical_solutions` 40 and `group_integration` 51; every one of the 255 tables had forced RLS and a `tenant_isolation` policy. All 42 designated evidence streams had the append-only trigger. The isolated instance was stopped and moved to macOS Trash after the probes. This proves migration behavior only, not external operating acceptance.

## External boundary

No repository check establishes external legal approval, financial correctness, board effectiveness, Agent production authority, model fitness, regulatory compliance, safety, partner readiness, Day 1 continuity, TSA exit, legacy retirement or finance-verified synergy. Those outcomes require the named human and system-of-record evidence and remain `NOT_RUN` or blocked.
