# Requirements and surrounding needs

## A. Core release needs

1. Build-once/promote-many immutable release.
2. OCI digest pinning; mutable tag only as a display alias.
3. SBOM + provenance + scan result attached to release.
4. Certification level and evidence digest bound to release.
5. Release retention, deprecation and revocation.

## B. Target onboarding

Support two product experiences:

### Bring Your Own ECS (P0)
User selects cloud connection, region and existing ECS instance(s). Elmos runs read-only capability discovery, then registers an immutable target identity.

### Create Environment (P1)
Elmos provisions infrastructure through IaC and then registers it as a target. Keep provisioning in a separate module from deployment.

Target discovery must capture:

- account/role ARN reference
- region/resource group
- instance IDs/tags
- VPC/vSwitch/security groups
- OS/architecture
- Cloud Assistant status/version
- Docker/runtime capability
- available CPU/memory/disk
- ingress/load balancer binding
- ACR network reachability

## C. Environment/config needs

Model dev/staging/prod as first-class environments.

Each environment owns:

- config version
- secret references
- domain/ingress
- database/service bindings
- rollout policy
- approval policy
- retention policy
- observability destination

Never bake environment secrets into images.

## D. Secrets

Separate:

- cloud control-plane credentials (RAM Role + STS)
- application secrets (KMS/Secrets adapter or customer secret system)
- registry auth
- database credentials

Evidence stores secret reference IDs and hashes where needed, never plaintext.

## E. Networking / domain / TLS

One-click deploy should eventually cover:

- security-group preflight
- internal vs public exposure
- port mapping
- Nginx/ALB/SLB integration
- DNS record plan/apply
- TLS certificate binding
- WAF/CDN optional integration

For Chinese-mainland public web targets, surface ICP readiness as a blocking/preflight concern instead of pretending deployment alone makes a public website launch-ready.

## F. Database / stateful dependencies

Production default:

- use external RDS/PolarDB/Redis or explicitly registered customer services
- do not silently run MySQL/Postgres/Redis inside the application Compose bundle
- allow containerized DB only for dev/demo/preview unless policy explicitly permits it

Migration orchestration must support Flyway, Liquibase, Alembic, Django migrations and EF Core migrations.

## G. Deployment strategies

P0:
- replace on single ECS
- compose bundle replace on single ECS
- manual promote after verification optional

P1:
- rolling batches across multiple ECS
- canary subset
- ALB/SLB drain/register
- blue/green groups

P2:
- ACK/Kubernetes/Helm
- autoscaling-aware rollout
- progressive delivery

## H. Health and acceptance verification

Layer probes:

1. instance/runtime health
2. container/process health
3. TCP port readiness
4. HTTP readiness/liveness
5. application smoke tests
6. optional externally routed E2E tests
7. optional business KPI/SLO observation window

A successful `docker start` is never sufficient.

## I. Rollback

Keep at least N previous stable release records and config versions.

Rollback triggers:

- command failure
- runtime health failure
- smoke/E2E failure
- rollout error budget breach
- operator request

Rollback may be blocked/partial when DB migration is incompatible. Escalate to `FAILED_NEEDS_HUMAN` with precise evidence.

## J. Observability

Attach deployment annotations to logs/metrics/traces:

- deployment_id
- release_id
- commit
- image digest
- environment
- target

P1 integrations may include SLS/CloudMonitor/OpenTelemetry.

## K. Cost and lifecycle

Surrounding product features:

- pre-deploy cost estimate for new resources
- environment TTL for preview/demo
- unused image cleanup/retention
- failed deployment cleanup
- old container/image disk GC
- per-tenant deployment usage and wall-clock metrics

## L. Product UX

One-click means low cognitive load, not absence of controls.

Recommended UI:

1. Select certified release
2. Select environment/target
3. Show generated deployment plan and risk summary
4. Resolve required config/secret references
5. Show DB migration classification
6. Approve/Deploy
7. Live step timeline
8. Health/smoke results
9. URL + release metadata
10. One-click rollback to eligible stable release

## M. Compliance / audit

Record actor, approver, role/session, policy decision, ticket, exact resource set, exact artifact digest and all mutations. Support exportable deployment evidence for customer audits.
