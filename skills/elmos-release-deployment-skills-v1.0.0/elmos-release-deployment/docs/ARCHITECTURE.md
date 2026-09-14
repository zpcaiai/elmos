# Architecture

## 1. Product position

Elmos Release Deployment is a shared platform plane used by all Elmos business lines:

- Spring legacy modernization
- repository-level cross-language conversion
- multi-language project generation
- SQL dialect/routine conversion when an application release depends on DB change

It turns a verified repository outcome into a running, verified system.

## 2. Trust domains

### Builder domain
May write application source, tests, Dockerfiles and draft deployment descriptors.
May not certify or directly mutate production.

### Truth Runner / Certifier domain
Runs tests, builds/verifies evidence and decides certification policy.
May not silently change application implementation.

### Release/Deployment domain
Consumes only certified immutable release inputs.
Mutates approved deployment targets through deterministic provider adapters.
Produces deployment evidence.

## 3. Major components

```text
CertifiedRelease Store
        |
        v
Deployment API/UI -> DeploymentTicket -> PolicyEngine
                                      |
                                      v
                              DeploymentWorkflow
                 +--------------------+-------------------+
                 |                    |                   |
          CredentialBroker      ArtifactRegistry     TargetRegistry
                 |                    |                   |
                 +---------- AlibabaEcsAdapter -----------+
                                      |
                              CloudAssistantExecutor
                                      |
                                DockerHostRuntime
                                      |
                  +-------------------+------------------+
                  |                   |                  |
          MigrationController  Health/Smoke Verify  TrafficController
                  |                   |                  |
                  +---------------- RollbackManager -----+
                                      |
                              DeploymentEvidence
```

## 4. Core principle: desired state + reconciliation

Do not model deployment as a long shell script. Persist desired state and reconcile remote state step by step. After a crash, read persisted state and continue safely.

Each remote mutation needs:

- deterministic operation key
- desired digest/config version
- provider request/invocation ID
- observed result
- retry policy
- compensation/rollback action

## 5. Alibaba execution modes

### Portable mode (P0 default)
Elmos orchestrates deployment, Cloud Assistant executes short deterministic templates, Docker pulls ACR images by digest. This remains portable to other clouds.

### Alibaba managed mode (P1 optional)
Adapter maps deployment to ECS Application Management / application publishing when the customer's account/features fit. Preserve the same Elmos domain contracts and evidence model.

## 6. Temporal mapping

Recommended workflows:

- `CreateReleaseWorkflow`
- `DeployReleaseWorkflow`
- `RollbackDeploymentWorkflow`
- `PromoteReleaseWorkflow`
- `DestroyPreviewEnvironmentWorkflow`

Activities must be idempotent. Long remote execution activities heartbeat and persist external invocation IDs.
