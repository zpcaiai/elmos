# Codex Execution Batches

These batches are implementation order, not completion claims. Every batch must land code + tests + evidence in the actual product repository.

## Batch 01 — Contracts, repository skeleton, CI guardrails
**Skills:** 00, 15, 16.  
**Code:** orchestrator/evidence/ci foundations; JSON-schema validation; run IDs; fingerprints.  
**Tests:** clean-checkout CI, schema negative tests, evidence tamper test.  
**Evidence:** CI log + evidence DAG fixture.  
**DoD:** a fake success report cannot pass without required evidence.

## Batch 02 — Assessment + Semantic IR
**Skills:** 01, 02, 03.  
**Code:** catalog model, typed IR, rule compiler, conflict detection.  
**Tests:** round-trip IR corpus, unknown-node preservation, rule collision.  
**Evidence:** parser/IR/rule coverage report.  
**DoD:** unknown syntax survives as explicit unsupported nodes; no silent loss.

## Batch 03 — Tier-1 source adapters
**Skills:** 20 Oracle, 21 SQL Server.  
**Code:** catalog extraction, parsers, session semantics, workload capture.  
**Tests:** package/procedure/trigger; T-SQL proc/temp/identity/error semantics.  
**Evidence:** extracted object count reconciliation.  
**DoD:** source catalogs reconcile and parsed coverage is quantified.

## Batch 04 — Tier-2 source adapters
**Skills:** 22–25.  
**Code:** PostgreSQL/MySQL/DB2/Sybase adapters.  
**Tests:** source-specific edge corpus.  
**Evidence:** adapter coverage matrix.  
**DoD:** each adapter fails closed on unsupported objects.

## Batch 05 — Data movement + DDL engine
**Skills:** 04, 05, 64.  
**Code:** chunking, CDC checkpoints, codecs, reconciliation, DDL planner/render contracts, vendor-tool bridges.  
**Tests:** resume, duplicate CDC, LOB, TZ, constraint ordering.  
**Evidence:** full-load+CDC test route with exact reconciliation.  
**DoD:** forced interruption resumes with zero loss/duplication in certified fixture.

## Batch 06 — SQL conversion engine
**Skill:** 06.  
**Code:** typed rewrite passes for functions/coercions/pagination/hierarchy/DML/locking/hints.  
**Tests:** differential query corpus including null/collation/time/ordering/concurrency.  
**Evidence:** per-rule differential coverage.  
**DoD:** regex-only conversion paths are rejected by code review/CI.

## Batch 07 — PL/SQL / T-SQL + lift-to-app engine
**Skill:** 07.  
**Code:** CFG, procedural strategies, package/trigger/dynamic-SQL handling, lift-to-app IR.  
**Tests:** Oracle package state/autonomous txn/bulk; T-SQL TRY/CATCH/temp/output.  
**Evidence:** compile or generated-app-plan + transaction diff.  
**DoD:** every procedural unit has an explicit strategy and verification path.

## Batch 08 — Application adapters
**Skills:** 08, 30–34.  
**Code:** Java/.NET/Python/Node/Go repository patch engines.  
**Tests:** framework fixture repos; dynamic/native SQL; driver/error/transaction changes.  
**Evidence:** clean builds + target integration tests.  
**DoD:** before/after vendor dependency counts and unresolved call sites are reported.

## Batch 09 — Transactional target adapters wave 1
**Skills:** 40 DM8, 41 KingbaseES, 42 openGauss, 47 HighGo.  
**Code:** target capability, types, DDL/SQL/proc render, error/plan/ops hooks.  
**Tests:** Oracle + T-SQL route corpora.  
**Evidence:** ephemeral apply/compile + E3 samples.  
**DoD:** exact version/mode capability snapshot gates rule loading.

## Batch 10 — Distributed target adapters wave 2
**Skills:** 43 TiDB, 44/45 GBase 8s/8c, 48/49 OceanBase, 50/51 GaussDB, 52 GoldenDB.  
**Code:** distributed semantics, movement hooks, mode/version features, lift-to-app paths.  
**Tests:** hotspot/skew/failover/transaction/concurrency.  
**Evidence:** target-specific E3/E4 smoke suites.  
**DoD:** TiDB procedural gaps route to decomposition; GoldenDB unknown capability fails closed.

## Batch 11 — Analytical target + benchmark lab
**Skills:** 46 GBase 8a, 10, 62.  
**Code:** analytical rewrite/physical design + workload benchmark framework.  
**Tests:** large join/aggregation/skew/load throughput.  
**Evidence:** comparable source/target benchmark manifests.  
**DoD:** target-optimized SQL is accepted only after result equivalence passes.

## Batch 12 — Behavioral verification + mutation quality
**Skills:** 09, 61.  
**Code:** differential runner, comparators, transaction/concurrency/side-effect probes, mismatch minimizer.  
**Tests:** deliberately wrong conversions must be detected.  
**Evidence:** mutation score and E3 report.  
**DoD:** critical mutation suite detection rate = 100%.

## Batch 13 — Guarded auto-repair
**Skill:** 11.  
**Code:** failure classification, patch generation/ranking, approval/rerun loop.  
**Tests:** safe vs high-risk repairs; regression rejection.  
**Evidence:** before/after E3/E4 and patch hash.  
**DoD:** no high-risk patch can self-approve or bypass tests.

## Batch 14 — Cutover / rollback / production certification
**Skills:** 12, 13, 14.  
**Code:** rehearsal/cutover/rollback, security mapping, E1-E5 policy engine.  
**Tests:** failed catch-up, partial deployment, rollback-after-target-writes, waiver expiry.  
**Evidence:** full rehearsal + certificate.  
**DoD:** a route cannot be certified when mandatory evidence is stale/missing.

## Batch 15 — Commercial control plane and reporting
**Skills:** 60, 63, 65.  
**Code:** truthful support matrix, estimates, operator API/dashboard metrics.  
**Tests:** route downgrade on version change, alert/gate status.  
**Evidence:** published support matrix tied to evidence IDs.  
**DoD:** sales-facing “production supported” status is computed only from unexpired certification.
