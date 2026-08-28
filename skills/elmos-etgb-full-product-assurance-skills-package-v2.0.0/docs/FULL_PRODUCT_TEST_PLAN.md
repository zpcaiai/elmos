# Elmos ETGB v2.0 Full-Product SOTA Test Plan

## 1. Assurance objective

ETGB v2.0 verifies the complete **declared** Elmos surface from user interface and public API through durable workflow, model/tool execution, data stores, billing/payment, artifacts, observability and release evidence. Correctness is defined as a conjunction of business behavior, state, side effects, authorization, financial reconciliation, recovery, performance and disclosure—not merely successful compilation or HTTP 2xx.

The suite contains **75,419 cases**. Feature coverage is governed by 1,452 registry entries, 23,232 direct feature bindings, 41 cross-domain journeys, 100 standards controls and 100 cross-cutting production scenarios.

## 2. Product domain matrix

| Domain ID | Scope | Features | P0/P1/P2 | Contexts | Cases | Production Adapter |
|---|---|---:|---:|---:|---:|---|
| `identity-access-tenant` | Identity, Access, Organization and Tenant Governance | 53 | 28/20/5 | 4 | 849 | `external-identity-access-harness` |
| `platform-control-plane` | Elmos Product Control Plane, Projects, Jobs and Administration | 66 | 33/27/6 | 4 | 1,057 | `external-control-plane-harness` |
| `repository-ingestion-context` | Repository, Archive and Context Ingestion | 64 | 34/25/5 | 4 | 1,024 | `external-ingestion-harness` |
| `multimodal-document-processing` | Multimodal File and Document Processing | 55 | 30/20/5 | 4 | 880 | `external-multimodal-processing-harness` |
| `ai-runtime-model-routing` | AI Runtime, Model Routing and Context Management | 67 | 37/25/5 | 4 | 1,073 | `external-ai-runtime-harness` |
| `agent-protocol-tooling` | Agent, Tool, MCP, A2A, AG-UI and Harness Protocols | 65 | 40/20/5 | 4 | 1,040 | `external-agent-protocol-harness` |
| `rag-memory-knowledge` | RAG, Knowledge Base, Search, Reranking and Memory | 67 | 37/25/5 | 4 | 1,073 | `external-rag-memory-harness` |
| `project-intelligence` | Repository Intelligence, Code Reading and Architecture Understanding | 71 | 39/27/5 | 4 | 1,137 | `external-project-intelligence-harness` |
| `online-ide-debug` | Online IDE, Build, Debug and Record-Replay | 65 | 37/23/5 | 4 | 1,041 | `external-online-ide-debug-harness` |
| `artifact-document-diagram` | Diagrams, Documents, Presentations and Delivery Artifacts | 65 | 36/24/5 | 4 | 1,040 | `external-artifact-render-harness` |
| `collaboration-integrations` | Collaboration, Git, Connectors and Enterprise Integrations | 56 | 30/21/5 | 4 | 896 | `external-collaboration-integration-harness` |
| `billing-entitlements` | Billing, Credits, Subscription, Pricing and Entitlements | 65 | 34/26/5 | 4 | 1,041 | `external-billing-ledger-harness` |
| `payment-finance` | Payment Providers, Refunds, Fraud Controls and Financial Consistency | 62 | 36/21/5 | 4 | 993 | `external-payment-sandbox-harness` |
| `api-sdk-webhook` | Public APIs, SDKs, CLI, Streaming and Webhooks | 62 | 36/21/5 | 4 | 992 | `external-api-sdk-harness` |
| `storage-search-cache` | Durable Storage, Object Artifacts, Search and Cache | 63 | 36/22/5 | 4 | 1,008 | `external-storage-search-cache-harness` |
| `deployment-operations` | Deployment, Kubernetes, Private Cloud, Observability and Disaster Recovery | 71 | 41/25/5 | 4 | 1,136 | `external-deployment-chaos-harness` |
| `security-privacy-compliance` | Application, AI, Agentic, Supply-Chain, Privacy and Compliance Assurance | 81 | 49/27/5 | 4 | 1,296 | `external-security-compliance-harness` |
| `ui-accessibility-localization` | Web User Experience, Accessibility, Responsive Design and Localization | 65 | 38/22/5 | 4 | 1,040 | `external-ui-accessibility-harness` |
| `analytics-admin-support` | Analytics, Administration, Support and Business Operations | 63 | 33/25/5 | 4 | 1,008 | `external-analytics-admin-harness` |
| `notifications-scheduler` | Notifications, Scheduled Jobs and Delivery Reliability | 46 | 25/16/5 | 4 | 736 | `external-notification-scheduler-harness` |
| `ai-solution-factory` | AI-Native Project Factory and Cross-Framework Agent Solution Compiler | 62 | 37/20/5 | 4 | 992 | `external-ai-solution-factory-harness` |
| `data-bigdata-solution` | Data Engineering, Streaming, Lakehouse and Analytics Project Capabilities | 59 | 34/20/5 | 4 | 944 | `external-data-platform-harness` |
| `commercial-delivery-certification` | Commercial Packaging, Evidence, Golden Routes and Customer Acceptance | 59 | 34/20/5 | 4 | 944 | `external-commercial-certification-harness` |

## 3. Four mandatory variants per product feature

1. **Nominal:** normal authorized behavior, expected output, state and audit.
2. **Boundary:** empty/maximum values, timeouts, quota edges, lifecycle edges and compatibility limits.
3. **Negative-security:** unauthenticated, unauthorized, cross-tenant, injection, malicious content, secret and replay paths.
4. **Concurrent-recovery:** duplicate delivery, parallel requests, partial commit, provider/worker loss, checkpoint resume and stale-fence rejection.

Each feature is exercised in every declared context. This creates **23,232** direct feature cases before journey, standards, fault and smoke campaigns.

## 4. Test pyramid and profiles

| Profile | Purpose | Required layers |
|---|---|---|
| `smoke` | deterministic offline integrity | local reference adapters and critical state/security/finance invariants |
| `pr` | affected functionality | risk-selected P0/P1, changed adapters, stable control sample |
| `nightly` | product integration | domain E2E, negative security, provider/DB/browser matrices |
| `weekly` | deeper quality | fuzz, mutation, multi-seed, compatibility and moderate performance |
| `release` | candidate certification | complete P0, required P1/P2, all adapters, journeys, controls and sealed evidence |
| `golden` | commercial route | large repositories, realistic data, customer holdout, rollback and repeatability |
| `exhaustive` | campaign/research | full matrix, extensive seeds, chaos, soak and uncommon environments |

## 5. Oracle portfolio

A critical case may combine:

- contract/schema/route/UI structure;
- clean build and independent tests;
- API/UI/CLI/model behavior;
- database, cache, queue, file, artifact and external-provider state;
- transaction, event order, retry, idempotency and fencing trace;
- authentication, authorization, tenant isolation and secret policy;
- ledger/provider/invoice/entitlement reconciliation;
- latency, throughput, resource, token, credit and wall-clock budgets;
- provenance, unsupported-function disclosure and evidence integrity.

No LLM judge is allowed to be the only Oracle for a P0 claim.

## 6. Cross-domain journey testing

The 41 journeys are executed for five personas—end user, organization administrator, developer/operator, support/finance and security/auditor—under happy path, partial failure and concurrent retry. The resulting 615 cases reconcile the complete causal chain rather than only browser success.

Representative flows cover registration and organization creation, repository upload and scan, transformation/generation execution, pause/resume/cancel, code reading/debug, RAG/document output, usage charging, payment/credit activation, webhook delivery, support remediation, deployment, incident recovery and commercial certification.

## 7. Security and AI assurance

Testing includes classic web/API/mobile controls and AI-specific threats:

- prompt and indirect injection;
- tool/Agent authority escalation;
- poisoned retrieval/memory;
- cross-tenant context leakage;
- insecure output handling;
- model/provider fallback and usage-accounting drift;
- excessive agency, recursive delegation and stale capability leases;
- hidden-test exfiltration and benchmark gaming;
- training/data-retention policy violations;
- supply-chain and artifact provenance failure.

## 8. Financial correctness

Every billable call requires reservation before execution, provider-usage identity deduplication, exactly-once ledger effect, cancellation settlement and independent reconciliation. Payment tests cover signed callbacks, duplicates, out-of-order events, partial/refund/chargeback states, entitlement activation, invoice/tax artifacts and no storage of prohibited card data.

Zero-tolerance outcomes include negative wallet balance, duplicate charge/credit, paid-to-pending regression, unexplained provider-to-ledger delta and cross-tenant financial access.

## 9. Reliability, performance and disaster recovery

Faults are injected before commit and after side effect for all 27 core/product domains. Campaigns include worker termination, lease expiry, network partitions, provider rate limits, database failover, object-store errors, event duplication/reordering, cache loss, disk pressure, secret rotation, deploy rollback and regional recovery.

Performance certification measures P50/P95/P99, throughput, error rate, queue delay, cold start, peak memory, CPU, storage I/O, token/credit and machine wall-clock. Large-repository routes include ≥500k LOC and ≥1M LOC candidates with shard resume and evidence retention.

## 10. Feature discovery and drift

Release CI must compare runtime routes, API operations, UI actions, jobs, event types, feature flags, entitlements and admin operations against the feature registry. A new implementation surface without a feature ID, owner, cases, Adapter and Oracle is an `UNDECLARED_FEATURE` and blocks release.

## 11. Release definition

A production candidate is test-complete only when:

- feature binding coverage is 100%;
- unavailable release cases and adapters are zero;
- all P0 critical Oracles pass and P0 SSER is zero;
- tenant, authority, data, payment and ledger violations are zero;
- required journey and control evidence is current;
- probabilistic tests meet seed/confidence requirements;
- performance and recovery budgets pass;
- evidence is sealed, complete and candidate-specific;
- corpus licenses and exact environment versions are approved.
