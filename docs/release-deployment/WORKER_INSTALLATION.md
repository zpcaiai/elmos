# Dedicated native worker installation

The repository implements an offline Linux rootless Docker execution backend in
`isolated_native_worker.py`. It composes with `NativeRunnerHost`, the canonical
dispatch ledger, host authorization and verified evidence ports. It creates no
new scheduler, identity service, secret store or certification authority.

## Required operator-provisioned environment

* Dedicated Linux user and local rootless Docker socket under
  `/run/user/<uid>/docker.sock`; rootful, remote and Windows daemons are rejected.
* Cgroup v2 with delegated CPU, memory and PID controllers and default seccomp.
* Digest-pinned Linux Docker CLI binary and a preloaded immutable worker image.
  Images are never pulled by a job. The image must contain the chosen executable
  at `/opt/elmos/bin/terraform` or `/opt/elmos/bin/helm`, have no declared volumes
  and no inherited environment other than PATH/LANG. Tool/provider provenance and
  independent approval of the exact image remain host responsibilities.
* Per-invocation private workspace, outside source checkouts, credential stores
  and Docker socket directories. The rootless UID mapping must give container
  UID/GID 65532 access to that workspace. Do not solve ownership failures by
  mounting the source repository or broadening filesystem permissions.
* Host supervisor cleanup after process/host crashes. Live command completion
  and cancellation forcibly remove the exact generated container name; abrupt
  host loss still requires orphan reconciliation. Container names are prefixed
  `elmos-deployment-`, with label `io.elmos.deployment-worker=true`. A label alone
  is not authorization to remove another tenant's work.

## Read-only installation probe

Install the engine with its `native` optional dependency in the host's pinned
Python environment. Create an operator-owned JSON config, not group/world
writable, with exactly these fields:

| Field | Value supplied by trusted installation |
| --- | --- |
| docker_binary | Absolute Linux Docker CLI path |
| docker_sha256 | `sha256:` prefixed digest of that exact CLI binary |
| socket | Local rootless `unix:///run/user/<uid>/docker.sock` |
| workspace | Absolute private workspace directory |
| image | Approved `registry/repository@sha256:<digest>` |
| tool | `terraform` or `helm` |

Run `elmos-deployment-worker-check --config /etc/elmos/native-worker.json`.
The probe validates the CLI bytes, daemon controls and local image metadata.
It performs no container creation, download or provider operation. Its output is
only `PREFLIGHT_PASSED`; container execution, authority installation, cloud
execution and certification remain unproven by this command.

## Bind to the existing host

Construct `PinnedNativeProcess` with the pinned Docker CLI and an environment
containing only the configured DOCKER_HOST. Wrap it with `IsolatedNativeProcess`.
Register an `IsolatedWorkerBinding` for the authenticated `Scope`, exact canonical
request digest, process and approved root Terraform configuration filenames.
Pass `IsolatedWorkerRegistry` as `NativeRunnerHost.workers`.

The request's runtime digest must equal the approved image manifest digest.
Terraform uses `approved.tfplan` in the private workspace; Helm uses `chart/`
and `values.json`. All are populated from verified artifacts by the trusted host,
with existing configuration/chart/values/lock/plan digest checks still enforced.
The registry cannot select an image, directory or tool from browser parameters.

Retain the actual host Authorization, signed attestation, canonical ToolCall
ledger and independent EvidenceVerifier bindings. NativeRunnerHost supplies each
resolved process with its own continuous authorization guard. Missing bindings
must fail startup/admission; fixture services are not installation substitutes.

## Execution and acceptance boundary

### Canonical secret materializer binding

The dedicated Java runtime service now includes `DeploymentSecretConfiguration`.
On the billing component, enable both `elmos.release-deployment.runtime-enabled`
and `elmos.release-deployment.secret-enabled`. Configure the trusted workspace map
under `elmos.release-deployment.secrets.workspaces` with each canonical workspace
identity mapped to its private Linux tmpfs directory. Roots must be disjoint,
process-owned, mode 0700 and free of symlink components. Secret files are created
exclusively with mode 0400; existing files are never overwritten.

The configuration constructs the existing `SecretInjectionService` with the new
`TmpfsSecretMaterializer`, and wires `DeploymentSecretSession`. The canonical
`SecretProviderPort`, durable `SecretLeaseStore` and
`DeploymentSecretSession.Authorization` remain mandatory injected services.
No provider, in-memory store or permissive authorization default is installed.
Missing provider bindings fail Spring startup. This does not add cloud STS/KMS
credential types or grant the offline container access to secret mounts.

The actual materializer was compiled and executed with Linux Java 21 against
`/dev/shm` in ELMOS-Test-Lab, using synthetic bytes only. The native harness checks
file bytes/0400 permissions, duplicate rejection, workspace and traversal denial,
disk and overlapping-root rejection, symlink rejection and idempotent cleanup.
Replay with `ELMOS_TEST_JAVA_HOME=/path/to/jdk21 python3 tooling/validate_release_tmpfs.py`.
Raw records and source/tool hashes are in `qualification/tmpfs-*`. This proves
local tmpfs behavior; it does not establish an installed credential service or
real cloud credential handling.

Each command runs with no network, read-only image, dropped capabilities,
no-new-privileges, non-root UID, 1 CPU, 512 MiB memory/no extra swap, 64 PIDs,
bounded output and temporary storage. The only host mount is the private
workspace. Daemon-reported container controls are checked before starting it.
Cancellation kills the attach client and then forcibly removes the container;
failed cleanup prevents success and requires reconciliation.

This backend supports offline Helm and provider-free/local Terraform only.
Cloud backend access, provider downloads, credential mounts and governed network
egress are not implemented by this backend. No arbitrary network option is exposed.
Actual isolated execution, crash/orphan recovery, host-service binding and cloud
acceptance still require the environment in LIVE_ACCEPTANCE_REQUIREMENTS.md.

Local checks found no Docker daemon on Windows and no Linux Docker daemon or
rootless tooling in the existing ELMOS-Test-Lab WSL environment. Tests using a
Docker protocol fixture remain local engineering evidence, not container runs.

Sandbox flag and rootless prerequisites were checked against
[Docker run documentation](https://docs.docker.com/engine/containers/run/) and
[Docker rootless documentation](https://docs.docker.com/engine/security/rootless/).
