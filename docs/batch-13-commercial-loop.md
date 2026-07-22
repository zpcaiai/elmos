# Batch 13 enterprise commercial loop

Repository scope was implemented on 2026-07-21. This document describes the cross-language migration roadmap's Batch 13; it is distinct from the older Java-engine Batch 13 composite-modernization numbering. Repository tests establish deterministic controls and artifact contracts only. Real CRM, CPQ, contract, billing, payment, accounting, customer, partner and production evidence remains `NOT_RUN` until the named external authority supplies it for the exact platform-business version.

## Outcome and reuse boundary

`modules/commercial-loop` implements the Enterprise Migration Commercial Operating Model (EMCOM). It admits an immutable, signed Batch 12 artifact that has externally reached T-G, verifies a complete commercial model, observes seven external evidence domains, and adjudicates B13-A through B13-G sequentially.

The module is not a CRM, CPQ, contract system, billing ledger, ticketing system or partner settlement engine. It cannot create a lead, opportunity, quote, contract, order, invoice, tenant, entitlement, support ticket, settlement, repository, Runner or production change. Its seven evidence-only ports are:

1. `SalesPocAuthority`
2. `QuoteContractAuthority`
3. `OnboardingDeliveryAuthority`
4. `SupportSuccessAuthority`
5. `PartnerAuthority`
6. `OperationsEconomicsAuthority`
7. `ScaleAcceptanceAuthority`

The older `modules/commercial-operations` domain and Flyway V10 remain authoritative for catalog, pricing, quotes, orders, subscriptions, entitlements, onboarding, migration projects, support, incidents, customer success, marketplace, revenue share and economics. V20 adds only the missing Batch 13 evidence projections. External CRM, finance and production systems remain their own systems of record.

## Unified operating model

EMCOM requires all eight business domains:

- `GO_TO_MARKET`
- `CUSTOMER_DISCOVERY`
- `SOLUTION_ENGINEERING`
- `COMMERCIAL_CONTRACT`
- `CUSTOMER_ONBOARDING`
- `DELIVERY_MANAGEMENT`
- `CUSTOMER_SUCCESS_SUPPORT`
- `PARTNER_REVENUE_OPERATIONS`

Every lifecycle record carries an account and opportunity identity, normal or exceptional stage, owner, entry and exit criteria, next action, date, risk, amount, technical scope and evidence. Exceptional outcomes such as disqualification, no decision, failed POC, security/budget/technical block, competitor loss, pause, churn risk and termination remain first-class states rather than disappearing from the funnel.

Exactly six commercial motions must be present and usable in the catalog, contract boundary and delivery/support model:

1. `direct-sales`
2. `poc-led-sales`
3. `enterprise-subscription`
4. `professional-services`
5. `partner-led-delivery`
6. `managed-migration-service`

## Non-compensating gates

| Gate | Required evidence |
| --- | --- |
| B13-A | Qualified discovery, independently bounded technical qualification, predefined POC criteria, controlled scope/budget, preserved failures and customer acceptance |
| B13-B | Versioned catalog and quote lineage, approved discount and margin, aligned proposal/SOW/contract/capability, immutable quote history, reconciled order/entitlement and no early billing |
| B13-C | Security-first identity/Runner/repository onboarding, customer owner, approved baseline, milestone/RAID ownership, scope control, versioned deliverables and acceptance evidence |
| B13-D | Sold-service SLA coverage, tenant-bound tickets, tested P1 escalation, incident/problem loop, customer health/value, renewal/churn intervention and safe non-renewal |
| B13-E | Partner diligence and certification, isolated least-privilege workspace, quality gate, no unauthorized access, reconciled settlement and governed marketplace assets |
| B13-F | Reconciled pipeline/forecast, visible delivery cost and project margin, usage-to-value linkage, stable metric definitions, concentration and owned commercial risks |
| B13-G | All six motions externally accepted, contractual capabilities aligned, complete evidence pack, full traceability and zero critical open commercial risk |

Evidence must be `PASSED`, complete, current, tied to the same assessment run and platform-business version, and returned by the proper authority. A future-dated, missing, wrong-run, wrong-version, inconclusive, failed or blocked envelope stops advancement. Authority exception details are reduced to the exception class so provider errors cannot leak credentials or customer data.

Critical blockers include discovery bypass; unscanned automation promises; undefined POC success or hidden POC failure; quote/SOW/contract mismatch; unauthorized discount or below-floor margin; security/SLA overcommitment; production source access before approval; missing customer owner or baseline; scope creep; absent deliverable/acceptance evidence; billing before acceptance; missed P1 escalation; churn risk without action; uncertified or overprivileged partner work; unreconciled settlement; missing cost/margin visibility; conflicting metrics; and ownerless critical risk.

`commercial_scale_ready=true` is a model invariant legal only at B13-G with all external evidence complete and no blocker. Every control-plane artifact records `commercial_operation_executed=false`.

## Artifacts and reports

`CommercialLoopArtifactWriter` writes the exact `commercial-platform/` hierarchy outside the source repository. It creates the go-to-market, solution-engineering, commercial, onboarding, delivery, support, customer-success, partners, revenue-operations, dashboards and reports subtrees. JSONL lifecycle/domain/motion streams are Zstandard-compressed. Every file is written atomically and append-only; pre-existing targets and symbolic-link traversal are rejected.

The exact report set is:

1. `icp-performance-report.json`
2. `sales-funnel-report.json`
3. `poc-conversion-report.json`
4. `quote-margin-report.json`
5. `onboarding-report.json`
6. `delivery-performance-report.json`
7. `sla-support-report.json`
8. `customer-health-report.json`
9. `renewal-report.json`
10. `partner-performance-report.json`
11. `profitability-report.json`
12. `value-realization-report.json`
13. `batch-13-conformance-report.json`

The writer also records the platform manifest, EMCOM control model, gate results, seven authority envelopes and one combined commercial evidence pack.

## Skills, contracts and storage

Skills 331–400 are 70 focused packages under `agent-skills/commercial-loop`. Every package has a validated `SKILL.md` and `agents/openai.yaml`; all packages read the shared evidence boundary in `agent-skills/commercial-loop/references/batch-13-commercial-loop.md`.

Sixteen Draft 2020-12 contracts under `contracts/commercial-loop-schema` cover the immutable Batch 12 artifact, lifecycle, domain and motion inputs, manifest, all seven evidence envelopes, evidence pack, quote, partner settlement and final conformance report. The conformance schema independently enforces the B13-G readiness invariant.

All 88 completion-definition questions are mapped individually to an owning Skill and required evidence in `docs/batch-13-commercial-loop-acceptance-checklist.md`. Repository implementation is recorded separately from field status; all real customer answers remain `NOT_RUN` until externally evidenced.

Flyway V20 creates 36 tenant-owned projections for missing lead, opportunity, discovery, solution, POC, stakeholder, contract assumption, engagement, wave, RAID, resource/time/cost, deliverable, acceptance, QBR/reference, partner, forecast, feedback, risk and value-realization evidence. Every table has organization ownership, source-system identity, version, owner, timestamps, idempotency, evidence references, forced RLS and tenant policy. Decision/result streams are append-only.

## Repository verification

```bash
JAVA_HOME=/opt/homebrew/Cellar/openjdk@21/21.0.11/libexec/openjdk.jdk/Contents/Home \
  /opt/homebrew/Cellar/maven/3.9.10/bin/mvn -pl modules/commercial-loop test

for schema in contracts/commercial-loop-schema/*.schema.json; do jq empty "$schema"; done

for skill in agent-skills/commercial-loop/*/SKILL.md; do
  python3 /Users/stephen/.codex/skills/.system/skill-creator/scripts/quick_validate.py "$(dirname "$skill")"
done
```

The focused suite covers the B13-G success path; Batch 12 admission; all domain and motion declarations; lifecycle entry criteria; authority sanitization and version binding; every blocker class across B13-A through B13-G; exact tree/report generation; Zstandard streams; append-only output; and direct, nested and ancestor symbolic-link rejection.

Recorded result: the focused module ran 48 tests with zero failures, errors or skips. The final 50-module `mvn clean test` reactor ran 646 tests with zero failures and zero errors; one existing Testcontainers wrapper test skipped because no container daemon was configured. All 70 Skills passed `quick_validate.py`, all 16 schemas parsed, and every local schema reference resolved.

The skipped database path was closed separately against a temporary PostgreSQL 17 instance. V1–V20 applied in numeric order and produced 1,147 public tables, 1,146 RLS-enabled and forced tables, and 1,146 tenant policies. All 36 V20 commercial projections existed; nine append-only triggers registered both UPDATE and DELETE events. A non-owner probe saw exactly one row in its selected tenant and zero cross-tenant rows, while an attempted update to `commercial_acceptances` was rejected.

## External acceptance boundary

Repository verification does not establish a real ICP conversion rate, POC outcome, discount approval, signed contract, order, entitlement, customer onboarding, source access, delivery milestone, billing event, SLA response, QBR, renewal, customer value, partner certification, settlement, margin, revenue or commercial-scale acceptance. All such field evidence remains `NOT_RUN`. Only approved external authorities evaluating the same signed platform-business artifact may close those gates.
