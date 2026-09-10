# 11 — MCP, Connector and Adapter Model

| Adapter | Providers | Scope |
|---|---|---|
| git-provider-adapter | GitHub/GitLab/Gitea/Azure Repos | repository source, pull requests, reviews, webhooks |
| artifact-storage-adapter | S3/GCS/Azure Blob/MinIO | content-addressed artifacts, evidence, retention and legal hold |
| issue-tracker-adapter | Jira/Linear/Azure Boards/GitHub Issues | requirements, risks, actions, findings and delivery status |
| documentation-adapter | Confluence/Notion/SharePoint/Google Drive | discovery evidence, specifications, ADRs and handoff documents |
| communication-adapter | Slack/Teams/Email | approved notifications, status, escalations and incident collaboration |
| calendar-meeting-adapter | Google Calendar/Microsoft 365/meeting systems | interviews, reviews, milestones and meeting evidence |
| crm-commercial-adapter | Salesforce/HubSpot | engagement context, qualification, account outcomes and product feedback |
| identity-directory-adapter | OIDC/SAML/SCIM/LDAP | identity, groups, authorization context and provisioning |
| secrets-kms-adapter | Vault/KMS/Secrets Manager | brokered secrets, signing keys and customer-managed encryption |
| policy-engine-adapter | OPA/Cedar/custom PDP | authorization, data use, release and evidence policy decisions |
| workflow-engine-adapter | Temporal/Cadence/Durable Functions | durable workflows, retries, timers, signals and compensation |
| sandbox-executor-adapter | container/microVM/WASI/remote runner | isolated build, analysis, tests and transformations |
| model-provider-adapter | OpenAI/compatible/private model endpoints | reasoning, generation, embeddings and judge candidates |
| compiler-lsp-adapter | compiler/LSP/tree-sitter/native parser | syntax, symbols, types, diagnostics and semantic edits |
| static-analysis-adapter | CodeQL/Semgrep/Sonar/native analyzers | rules, dataflow, taint, architecture and quality findings |
| dependency-sbom-adapter | Syft/Trivy/OSV/Dependency-Track | SBOM, vulnerabilities, license and provenance inputs |
| test-runner-adapter | JUnit/pytest/dotnet test/go test/cargo test | test discovery, execution, coverage and result normalization |
| fuzz-mutation-adapter | property/fuzz/mutation engines | oracle strength, counterexamples and robustness evidence |
| database-adapter | PostgreSQL/MySQL/Oracle/SQL Server/NoSQL | schema, plans, routines, snapshots, migration and reconciliation |
| messaging-stream-adapter | Kafka/Pulsar/RabbitMQ/cloud queues | topics, schemas, replay, ordering, delivery and side effects |
| observability-adapter | OpenTelemetry/Prometheus/Grafana/APM | traces, metrics, logs, profiles, SLOs and incidents |
| cloud-kubernetes-adapter | AWS/Azure/GCP/Kubernetes | inventory, IAM, network, deployment, scaling and cost |
| iac-gitops-adapter | Terraform/Pulumi/Helm/ArgoCD/Flux | infrastructure semantics, drift, plans and controlled rollout |
| security-scanner-adapter | SAST/DAST/IaC/container/secret scanners | security signals and remediation verification |
| service-virtualization-adapter | WireMock/MockServer/Testcontainers/custom | external dependency simulation and deterministic replay |
| billing-metering-adapter | usage ledger/invoice/credits | cost attribution, quotas, budgets and commercial metering |

## Rules

Adapters negotiate capabilities and versions; receive host-minted verified security context and an invocation-scoped lease; execute only in the owning environment; return typed results; support cancellation/idempotency; and are fenced after replacement. Secrets stay tool-side. An Adapter can produce evidence but cannot own routing, semantic truth or completion.

MCP tools should expose coarse, business-safe operations rather than raw unrestricted shell/database access. Read and write operations are separate; side-effecting tools require explicit hints, policy and approval.
