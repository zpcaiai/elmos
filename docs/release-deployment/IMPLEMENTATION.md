# Release deployment implementation

This repository-owned implementation consumes the pinned package as a specification,
not as executable instructions. The source ZIP has SHA-256
`e5c4dea07a6897c0b5804de6c992714860a5aca0f8d66377da2fe1241a8ca85a`.
Its 24 files are mirrored unchanged. Package examples contain placeholder digests
and unsigned certification/ticket assertions and are not accepted by the runtime.

## Run local qualification

```powershell
uv run --no-project --with cryptography==46.0.7 --with jsonschema==4.25.1 --with temporalio==1.32.0 python tooling/validate_release_deployment.py --opa .elmos/release-deployment-tools/opa_windows_amd64.exe
```

The OPA option is optional. An omitted OPA binary records OPA execution as NOT_RUN.
The Windows OPA 1.0.0 binary used during development has SHA-256
`f910bc4f4e27fe27f861ec3ea4ec58ca859ec7245007df4d3ab6d53058745991`, checked against
the upstream release checksum. No tool is downloaded or executed from the source
archive. The qualifier runs real local SQLite, Ed25519, loopback HTTP, Python
contract/failure-injection tests, Temporal SDK registration, and optional OPA tests.
Docker command tests inject a runner. Provider tests use explicit test transports.
These are not ECS/ACR/container/Temporal-server or independent acceptance results.

## Runtime composition

`ReleaseDeploymentService` owns immutable release/target/config/plan registrations,
signed tickets, separate production approval, revocation and deployment admission.
`DeploymentWorkflow.tick` performs one durable reconciliation phase. It composes
the host authority, execution and evidence ports from `ports.py`. It does not mint
identity or certification. `DeploymentAPI` is a WSGI application to mount inside
the authenticated host, not a new public authentication service. The host must
construct `Principal` from verified identity/resource bindings and enforce its
normal session, CSRF, origin, rate and tenant controls. JSON scope is rejected.

Mandatory host bindings:

| Engine port | Existing repository boundary | Required binding |
| --- | --- | --- |
| Principal resolver | `modules/identity`, authenticated application principal | Full tenant/workspace/project/environment/account + permissions |
| AuthorizationHost | `modules/continuous-authorization`, identity/credential leases | Ticket issuance, independent approval, current policy/revocation, scoped lease |
| ExecutionHost | `ProductionToolCallPort` in `modules/production-runtime`, secure execution plane | begin, claimProviderDispatch, accepted/unknown/result and reconciliation |
| EvidenceHost | `modules/cas`, `modules/evidence-assurance-fabric` | Immutable digest-bound commit and verified receipt |
| TrustVerifier | Host trusted key registry | Purpose-specific verification and revocation |
| Deployment journal | Host persistence boundary | Durable transactions, environment/resource mutexes, account quotas |

These are explicit integration ports. **The new WSGI routes and host adapters are
not wired into the running Java control plane by this package.** The supplied
SQLite journal is a local backend; production PostgreSQL/HA wiring is still needed.
No in-memory fixture authority or test HMAC key may be installed in production.

`temporal_adapter.definitions(engine, principal_lookup)` returns a workflow and an
activity for host Worker registration. Workflow input is a deployment ID. Identity
comes from trusted lookup. Retries run reconciliation; they do not directly retry
remote commands. Register the worker/task queue using host configuration. A real
Temporal server restart/cancellation test remains required.

## Durable failure semantics

Every operation is recorded as DISPATCHING before submission. An invocation ID is
saved as soon as available. A crash between claim and submission or between
submission and receipt leaves uncertainty. Only `ExecutionHost.recover` may resolve
the existing operation key through the canonical dispatch ledger. Polling never
submits again. UNKNOWN cannot pass verification or release resource locks.

State CAS prevents racing ticks from overwriting a later phase. Account-wide
quota, environment mutex and physical target locks are acquired in one transaction.
Tickets cannot authorize two independent deployments. Identical request keys return
the same deployment; conflicting content is rejected. Unsafe terminal outcomes
retain locks for explicit host reconciliation. No automatic lock expiry authorizes
an overlapping production mutation.

Health/smoke failures after a known mutation trigger snapshot-based rollback.
Rollback restores exact images, config and traffic, and verifies the previous
snapshot's health policy. An operator rollback creates a new deployment and needs
a fresh approved ticket. Prior success evidence remains immutable. A deployment
becomes SUCCEEDED only after a verified host evidence commit and a local atomic
evidence/state transaction.

## Deterministic remote agent

Install the Python project on a dedicated Linux host to expose
`elmos-deployment-agent`. Provision, through the trusted host deployment process:

* `/etc/elmos/deployment-trust.json`, root-owned and not group/world writable,
  containing pinned Ed25519 public keys, revocations, exact scope and instance ID;
* `/var/lib/elmos/permits/<sha256>.json`, a signed remote permit;
* `/var/lib/elmos/bundles/<sha256>.json`, byte-exact canonical Compose output;
* `/var/lib/elmos/config/<sha256>`, digest-verified runtime config bytes;
* `/run/elmos/secrets/<reference-sha256>`, host-resolved, scoped secret files.

Secret mount keys hash the complete scope key plus versioned secret reference.
`SecretResolver` writes owner-only, immutable files from the canonical secret
fetcher. `RedactingEvidenceCapture` removes supplied secret values, base64/URL
variants and authorization headers before storing bounded logs in scoped CAS.
Cloud account ID is a target property distinct from the platform account ID used
for account-wide concurrency. Neither is accepted as browser-minted authority.

The agent has no installer, credential discovery, arbitrary shell or policy bypass.
It verifies permit scope/instance/action/expiry/signature, regenerates Compose from
typed artifacts, and rejects mismatched bytes, tags and privileged settings. It
runs fixed argv commands with no captured raw logs. Its monotonic **physical-host**
fence must come from the host credential/lease service; it is not a client version
or a per-deployment phase counter. A subprocess timeout/crash leaves UNKNOWN and
blocks subsequent mutations pending reconciliation. The current agent exposes no
automatic UNKNOWN clearance. Health probes are bounded loopback HTTP GETs without
redirect following; production functional probes are an additional host boundary.

The agent's preflight implementation currently checks bundle/config integrity,
permission/fencing and disk capacity. Full ECS/user/runtime/memory/network/secret,
TLS/ICP and external stateful-service checks are required from `target.preflight`.
No successful Docker start alone can satisfy deployment health or smoke gates.

## Exact implementation coverage and remaining work

| Work package | Repository implementation | Remaining integration / runtime evidence |
| --- | --- | --- |
| RD-00 | Typed contracts, state machine, SQLite transactions | Production persistence adapter |
| RD-01 | Exact signed certification/release bridge, revoke | Bind real Assurance verdict and CAS objects |
| RD-02 | Ticket issue/approve/revoke/expiry + OPA rules | Host policy/signature/RBAC service wiring |
| RD-03 | Signed target registry + ECS/assistant mapping + bounded signed HTTPS RPC | Canonical session broker wiring and live account/resource probe |
| RD-04 | Scoped leases + STS request/session policy | Canonical broker/session vault wiring |
| RD-05 | OCI manifest/config byte verification by digest | ACR-authenticated blob fetcher |
| RD-06 | RunCommand/poll/cancel mapping, scoped log redaction + durable host recovery port | SDK transport, signed remote permit delivery, canonical CAS wiring |
| RD-07 | Canonical Docker/Compose + executable Linux agent | Four real language image deployments; full runtime preflight |
| RD-08 | Typed config validation, reference-only secrets and scoped owner-only file materialization | Canonical KMS secret fetcher and host tmpfs provisioning |
| RD-09 | Five-tool typed migration IR classification and policy gates | Native tool discovery/IR extraction, execution, backup/restore adapters |
| RD-10 | Bounded retry/deadline probes, exact case sets, loopback HTTP | Representative application/business probes |
| RD-11 | Automatic and manual immutable rollback workflow | Live provider snapshot/restore/traffic adapters |
| RD-12 | Signed operation receipts, raw-log hashes/references and immutable schema-valid evidence | Canonical CAS/evidence host integration |
| RD-13 | Durable reconciliation and Temporal workflow/activity definitions | Java worker registration, PostgreSQL/HA and real Temporal execution |
| RD-14 | Three backend profiles + Vue in canonical Compose | Real external DB configuration and container runs |
| RD-15 | P0 WSGI API + Spring authenticated host mount, exact-byte Ed25519 bridge, durable replay checks | Operator binding configuration, complete authority/execution/evidence adapters, product UI |
| RD-20 | Exact bounded rolling batches with batch verification | Live multi-ECS rollout execution |
| RD-21 | ALB ECS backend weight execution, before-image checks, durable dispatch, asynchronous readback and separately approved compensation | SLB variants, trusted health gate integration and real traffic journeys |
| RD-22 | Exact Alibaba DNS record update/readback and separately approved compensation; DNS/TLS planning boundaries | TLS certificate/listener execution and external resolver convergence |
| RD-23 | Exact IaC plan authorization and destroy binding | IaC native plan/apply/destroy executor |
| RD-24 | Signed exact scan/signature verdict checks | ACR scanner and signature provider |
| RD-25 | Immutable TTL, resource reconciliation and retention selection | Provisioning/cleanup scheduler and provider effects |
| RD-26 | Allowlisted deployment annotations | SLS/CloudMonitor/OTel exporter wiring |
| RD-30 | Restricted existing Deployment SSA execution and pinned-CA HTTPS transport; UID/version/generation/admission/rollout checks | ACK discovery, namespace provisioning, canonical token broker and real cluster journeys |
| RD-31 | Restricted Helm-rendered manifest/GitOps proposal validation | Sandboxed Helm render, SCM proposal and GitOps reconciliation |
| RD-32 | Exact-decimal SLO window/error-budget decision | Trusted telemetry collection and progressive workflow integration |
| RD-33 | Exact provider/version/region/account/action registry | Concrete additional cloud provider adapters |

ALB traffic, DNS record updates and existing Kubernetes Deployment updates now
have executable controllers as well as planning components. Their host brokers and
live integration remain required; the other P1/P2 rows retain the gaps above.
The entire source package is **not yet functionally complete**.
This matrix intentionally distinguishes real code, host integration and live
acceptance rather than treating interfaces or passing local tests as full delivery.
No cloud environment is needed to continue closing the listed host integration and
product gaps. Cloud credentials/resources are needed only for the live tests.

## Java host bridge configuration

`ReleaseDeploymentController` mounts
`/api/v1/release-deployment/{environment}/v1/...` in `apps/control-plane`.
It requires the existing database-bound `ControlPlanePrincipal`, primary tenant
membership and `workspace:view`, then an explicit actor grant in the operator-owned
environment binding. It does not grant deployment rights to every workspace viewer.
Unsigned browser identity headers and scope fields do not supply authority.

Enable with `elmos.release-deployment.enabled=true` and provide
`elmos.release-deployment.configuration-file` plus
`elmos.release-deployment.signing-key-file`. Both files must be operator-owned,
non-symlink, bounded and owner-only (Windows permits SYSTEM/Administrators too).
The signing key file contains base64 PKCS#8 Ed25519 bytes; never commit it.
Configuration shape (values below are illustrative, not credentials or grants):

```json
{
  "endpoint": "https://deployment-worker.internal",
  "audience": "elmos-deployment-worker",
  "keyId": "deployment-host-v1",
  "environments": {
    "staging": {
      "scope": {
        "tenant_id": "tenant-id", "workspace_id": "workspace-id",
        "project_id": "project-id", "environment_id": "staging",
        "account_id": "platform-account-id"
      },
      "actorPermissions": {"database-bound-actor-id": ["deployment:read"]}
    }
  }
}
```

Compose `DeploymentAPI(service, SignedHostAuthenticator(keys, replay_store,
audience), discovery)` in the worker. `keys` maps each host key ID to its raw
Ed25519 public key bytes and the exact allowlisted `Scope.key` values. Use a durable
`ReplayStore` path shared by all local worker processes. Multi-node replicas require
a shared transactional replay backend before enabling HA. The bridge signs method,
path, SHA-256 of exact body bytes, actor, scope, grants, nonce and a 30-second expiry;
workers cap leases at 60 seconds. HTTPS authenticates the response endpoint. Host
configuration/key/grant changes currently require process restart.

`DeploymentToolExecutor` in `modules/production-runtime` reuses
`ProductionToolCallPort` and `JdbcDeploymentToolReceiptLookup` over the canonical
`ai_usage.tool_calls`/receipt tables. Lookup binds account, project, job, stage,
work item, attempt, action and payload hash under the existing tenant RLS context.
The executor claims dispatch before sending, never reuses `begin` to poll an
accepted/unknown call, and requires the separate evidence verifier before CAS
artifact completion. Production composition must supply current authorization,
exact provider adapters and the independent evidence verifier; no permissive
default implementations are installed. Its unit tests use an explicit local
ledger fixture; the JDBC lookup still requires representative PostgreSQL/RLS
integration testing before rollout.

`AlibabaRpcTransport` supports only its enumerated ECS, ALB and Alibaba DNS actions.
Its host broker must implement `authorize_call(lease, exact_request)` and
`record_response(...)`, backed by canonical authorization, credential and tool-call
services. `KubernetesHttpsTransport` similarly requires a scoped cluster token broker.
These transports never resolve credentials from environment variables, retry writes,
follow redirects, change network/IAM policy or treat an API readback as certification.
DNS readback is not proof of resolver propagation; Kubernetes rollout is not a
substitute for application smoke tests.

Protocol references:
[ALB backend updates](https://www.alibabacloud.com/help/en/slb/application-load-balancer/developer-reference/api-alb-2020-06-16-updateservergroupserversattribute),
[RPC signing](https://www.alibabacloud.com/help/en/sdk/product-overview/rpc-mechanism),
[Kubernetes SSA](https://kubernetes.io/docs/reference/using-api/server-side-apply/).

## Evidence and authority

All 25 source acceptance scenarios stay NOT_RUN until their real target environment
and raw execution evidence exist. The local qualifier is self-attested engineering
evidence. Only the applicable Batch 38 gate and separate external authority can
decide readiness/certification. Package status remains NOT_CERTIFIED.

Provider mappings were checked against primary references:
[RunCommand](https://www.alibabacloud.com/help/tc/ecs/api-runcommand),
[DescribeInvocationResults](https://www.alibabacloud.com/help/en/ecs/developer-reference/api-ecs-2014-05-26-describeinvocationresults),
[DescribeCloudAssistantStatus](https://www.alibabacloud.com/help/en/ecs/developer-reference/api-ecs-2014-05-26-describecloudassistantstatus),
[STS constraints](https://www.alibabacloud.com/help/en/ram/support/faq-about-ram-roles-and-sts-tokens),
[OPA testing](https://www.openpolicyagent.org/docs/policy-testing), and
[Kubernetes API concurrency](https://kubernetes.io/docs/reference/using-api/api-concepts/).
