# Full-Product Adapter Implementation Status

## Interpretation

All cases are materialized and resolve to an Adapter contract. `implementation-required` means the contract and cases exist but a real Elmos worker/provider/browser/database/payment environment has not been certified by this package build. Such cases are allowed for planning but block a release execution.

| Adapter | Domain | Current package status | Release requirement |
|---|---|---|---|
| `external-identity-access-harness` | `identity-access-tenant` | `implementation-required` | exact candidate/environment conformance and sealed evidence |
| `external-control-plane-harness` | `platform-control-plane` | `implementation-required` | exact candidate/environment conformance and sealed evidence |
| `external-ingestion-harness` | `repository-ingestion-context` | `implementation-required` | exact candidate/environment conformance and sealed evidence |
| `external-multimodal-processing-harness` | `multimodal-document-processing` | `implementation-required` | exact candidate/environment conformance and sealed evidence |
| `external-ai-runtime-harness` | `ai-runtime-model-routing` | `implementation-required` | exact candidate/environment conformance and sealed evidence |
| `external-agent-protocol-harness` | `agent-protocol-tooling` | `implementation-required` | exact candidate/environment conformance and sealed evidence |
| `external-rag-memory-harness` | `rag-memory-knowledge` | `implementation-required` | exact candidate/environment conformance and sealed evidence |
| `external-project-intelligence-harness` | `project-intelligence` | `implementation-required` | exact candidate/environment conformance and sealed evidence |
| `external-online-ide-debug-harness` | `online-ide-debug` | `implementation-required` | exact candidate/environment conformance and sealed evidence |
| `external-artifact-render-harness` | `artifact-document-diagram` | `implementation-required` | exact candidate/environment conformance and sealed evidence |
| `external-collaboration-integration-harness` | `collaboration-integrations` | `implementation-required` | exact candidate/environment conformance and sealed evidence |
| `external-billing-ledger-harness` | `billing-entitlements` | `implementation-required` | exact candidate/environment conformance and sealed evidence |
| `external-payment-sandbox-harness` | `payment-finance` | `implementation-required` | exact candidate/environment conformance and sealed evidence |
| `external-api-sdk-harness` | `api-sdk-webhook` | `implementation-required` | exact candidate/environment conformance and sealed evidence |
| `external-storage-search-cache-harness` | `storage-search-cache` | `implementation-required` | exact candidate/environment conformance and sealed evidence |
| `external-deployment-chaos-harness` | `deployment-operations` | `implementation-required` | exact candidate/environment conformance and sealed evidence |
| `external-security-compliance-harness` | `security-privacy-compliance` | `implementation-required` | exact candidate/environment conformance and sealed evidence |
| `external-ui-accessibility-harness` | `ui-accessibility-localization` | `implementation-required` | exact candidate/environment conformance and sealed evidence |
| `external-analytics-admin-harness` | `analytics-admin-support` | `implementation-required` | exact candidate/environment conformance and sealed evidence |
| `external-notification-scheduler-harness` | `notifications-scheduler` | `implementation-required` | exact candidate/environment conformance and sealed evidence |
| `external-ai-solution-factory-harness` | `ai-solution-factory` | `implementation-required` | exact candidate/environment conformance and sealed evidence |
| `external-data-platform-harness` | `data-bigdata-solution` | `implementation-required` | exact candidate/environment conformance and sealed evidence |
| `external-commercial-certification-harness` | `commercial-delivery-certification` | `implementation-required` | exact candidate/environment conformance and sealed evidence |
| `external-product-journey-harness` | `product-journey` | `implementation-required` | exact candidate/environment conformance and sealed evidence |
| `external-standards-assurance-harness` | `standards-assurance` | `implementation-required` | exact candidate/environment conformance and sealed evidence |

## Existing repository-engineering adapters

The original external transformation, repository translation, project generation/evolution/requirement reasoning, dual-database and fault-injection adapters remain required. The local reference Runner only executes deterministic fixture adapters.

## Coding-complete criteria

An Adapter is not complete merely because a class or endpoint exists. It must pass:

1. schema and capability negotiation;
2. authority, lease and fencing negative tests;
3. idempotent phase replay;
4. pause/resume/cancel/crash recovery;
5. raw evidence and OpenTelemetry correlation;
6. exact version and dependency provenance;
7. cleanup/retention behavior;
8. domain Oracle conformance;
9. load, chaos and tenant-isolation campaigns;
10. release execution with unavailable count zero.
