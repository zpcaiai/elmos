---
name: elmos-release-deployment
description: Implement Elmos proof-driven release and deployment from certified repository outputs to Alibaba Cloud ECS, with immutable OCI artifacts, deployment tickets, Cloud Assistant execution, layered verification, evidence, rollback, and multi-tenant safety.
---

# Elmos Release Deployment Skill

## Mission

Build the production-grade Elmos release/deployment plane that consumes only certified releases and deploys them safely to Alibaba Cloud ECS. P0 supports Spring Boot, Vue, Python, and .NET through OCI images and ACR, using Cloud Assistant as the remote executor. The core must remain provider-neutral so Alibaba ECS is an adapter, not the domain model.

## Non-negotiable invariants

1. Never deploy an unverified workspace directory, mutable `latest` tag, or Builder/LLM assertion.
2. Deploy only a `CertifiedRelease` whose source commit, artifact digest, certification evidence, and policy decision are bound together.
3. Every production deployment requires a `DeploymentTicket` bound to tenant/project/environment/target/artifact digest and an expiration time.
4. Cloud credentials must be short-lived. Prefer RAM Role + STS; do not persist Alibaba Cloud account/root AccessKeys.
5. Remote execution is fenced by an invocation-scoped `CapabilityLease`; the executor may only touch ticket-authorized resources.
6. Commands must be deterministic templates. Do not permit arbitrary LLM-generated production shell execution.
7. Every side effect must be idempotent and resumable. Persist operation keys and provider request IDs.
8. Production deployments must have preflight, health verification, smoke verification, evidence, and rollback policy.
9. Application rollback and database rollback are different. Destructive DB migrations require an explicit policy/approval path.
10. A deployment is not SUCCESS until post-deploy verification passes and immutable `DeploymentEvidence` is committed.
11. Builder/LLM may propose a plan; deterministic release/deployment workers execute and attest it.
12. Never overwrite prior deployment evidence; evidence is append-only/immutable.

## Architecture boundary

Core domain must depend on these SPIs, never Alibaba SDK types:

- `ReleaseStore`
- `ArtifactRegistry`
- `DeploymentProvider`
- `CredentialBroker`
- `RemoteExecutor`
- `HealthVerifier`
- `MigrationController`
- `TrafficController`
- `RollbackManager`
- `EvidenceStore`
- `PolicyEngine`
- `SecretResolver`
- `ObservabilityPublisher`

Alibaba-specific implementations belong under `adapters/alibaba/*`.

## P0 target

Implement:

- `CertifiedRelease`
- `ReleaseManifest`
- `DeploymentTarget`
- `DeploymentTicket`
- `DeploymentPlan`
- `CapabilityLease`
- `AlibabaEcsAdapter`
- `AlibabaStsCredentialBroker`
- `CloudAssistantExecutor`
- `AcrArtifactRegistry`
- `DockerHostRuntime`
- `HealthVerifier`
- `SmokeVerifier`
- `MigrationController`
- `RollbackManager`
- `DeploymentEvidence`
- `DeploymentWorkflow`
- OPA deploy gate

P0 deployment shapes:

1. Single OCI service -> one existing ECS instance.
2. Full-stack bundle -> one existing ECS instance using versioned Compose manifest (Spring/.NET/Python backend + Vue/Nginx frontend; stateful production databases external by default).
3. Static Vue frontend -> Nginx OCI image -> ECS.

## Execution workflow

`REQUESTED -> POLICY_CHECKED -> PREFLIGHT -> LEASED -> ARTIFACT_RESOLVED -> MIGRATION_PREFLIGHT -> DEPLOYING -> RUNTIME_HEALTH -> SMOKE_VERIFY -> TRAFFIC_PROMOTION -> EVIDENCE_COMMIT -> SUCCEEDED`

Any failure after mutation enters:

`FAILED -> ROLLBACK_PLANNED -> ROLLING_BACK -> ROLLBACK_VERIFY -> ROLLED_BACK`

If state cannot be proven safe:

`FAILED_NEEDS_HUMAN`

## Required preflight

Check before any mutation:

- ticket signature/status/expiry
- tenant/project/environment scope
- release digest and evidence digest
- OPA policy decision
- target ECS existence and Running state
- target belongs to authorized region/resource group/tags
- Cloud Assistant installed/healthy
- deployment user available and permitted
- Docker/container runtime version
- free disk/memory/ports
- registry reachability and image availability by digest
- configuration schema completeness
- secret references resolvable without exposing values
- domain/ingress dependencies
- DB migration classification and backup requirement
- previous stable release exists when rollback is required

## Build/release rules

Build is not deployment. Build once and promote the same digest across environments.

For each release produce:

- immutable OCI digest
- SBOM digest (CycloneDX or SPDX)
- build provenance digest
- vulnerability scan result/ref
- verification evidence digest
- runtime config schema
- migration manifest
- health policy
- rollout compatibility metadata

## Language profiles

### Spring Boot
- Default runtime: Java 21/25-compatible image selected by project constraints.
- Health: Spring Boot Actuator endpoint where available.
- DB migration detection: Flyway/Liquibase.
- Never bundle production DB in the app container.

### Vue
- Build static assets once.
- Serve from immutable Nginx image.
- Health: HTTP GET `/` plus optional asset hash check.
- Runtime API endpoint injection must use a deterministic config mechanism, not rebuild source in production.

### Python
- Prefer locked dependencies (`uv.lock`, Poetry lock, or pinned requirements).
- Run as non-root.
- Health endpoints for FastAPI/Flask/Django profiles.
- Detect Alembic/Django migrations.

### .NET
- Use multi-stage publish.
- Run as non-root where base image allows.
- Detect EF Core migrations.
- Health endpoint via ASP.NET Core health checks when available.

## Database policy

Classify migrations:

- `SAFE_EXPAND`: additive tables/columns/indexes compatible with old app.
- `CONDITIONAL`: long-running index/backfill/constraint operations.
- `DESTRUCTIVE`: drop/rename/narrow type/data rewrite that breaks old version.

Production defaults:

- allow `SAFE_EXPAND` with normal ticket
- require explicit approval + backup evidence for `CONDITIONAL`
- deny automatic `DESTRUCTIVE` deploy unless a dedicated migration ticket and rollback/restore plan exist

Prefer Expand -> Deploy compatible app -> Backfill -> Verify -> Contract in a later release.

## Remote execution rules

Cloud Assistant is a transport, not authority. Keep command templates small and versioned. The command should fetch/resolve a signed deployment bundle or pull OCI images by digest, then execute only ticket-approved operations.

Never put secrets in command text, stdout, evidence logs, or Docker CLI arguments where they can be exposed. Resolve secret references at runtime through the approved secret adapter.

## Rollback rules

Rollback must restore:

- previous OCI digest(s)
- previous config version
- traffic mapping
- compatible migration state, or declare manual intervention required

Rollback verification must rerun runtime health + smoke tests. A rollback is not successful merely because the previous container started.

## Evidence requirements

Persist at least:

- deployment_id / ticket_id / release_id
- tenant/project/environment
- commit + image digest(s)
- evidence/certification digest
- target resource IDs
- credential/session identity metadata (never secret material)
- Cloud Assistant invocation IDs
- step start/end/duration/exit code
- redacted stdout/stderr hash + artifact URI
- health/smoke case results
- migration results
- traffic changes
- rollback actions
- final state
- signatures/attestations

## Multi-tenant rules

Isolation key is `(tenant_id, workspace_id, project_id, environment_id)`.

Enforce:

- per-account max concurrent deployments
- per-environment deployment mutex
- idempotency key uniqueness
- target ownership verification
- environment-specific RBAC
- production approval policy
- tenant-scoped secrets and registry credentials
- no cross-tenant cache entries containing secret/config material

## Required implementation order

Follow `work-packages/WORK_PACKAGES.md`. Do not skip dependency order. For each package:

1. implement domain and interfaces
2. add unit tests
3. add contract tests
4. add failure-injection tests
5. produce Truth Runner evidence
6. update package status only after evidence exists

## Definition of done

P0 is complete only when all acceptance cases in `acceptance/ACCEPTANCE.md` pass, including failed health check auto-rollback, expired ticket rejection, target-fencing rejection, retry after orchestrator crash, secret redaction, and DB destructive migration denial.
