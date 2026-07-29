# Git repository workspaces

ELMOS can create a bounded local workspace from GitHub, Gitee, or another
HTTPS Git server. The workspace is resolved to an advertised exact commit
before checkout and can inventory, read, and modify UTF-8 text files including:

- source code and tests;
- Markdown and other documentation;
- YAML, JSON, TOML, XML, properties, and similar configuration;
- Docker and Compose local deployment files;
- GitHub Actions, GitLab CI, Kubernetes, Helm, and Terraform cloud deployment
  files.

Creating a workspace or saving a file ends at a local diff. Commit, Push, and
Pull Request are separate permission-checked actions with exact path, HEAD,
remote-ref, short-lease, audit, and idempotency checks. ELMOS never force
pushes, merges, deploys, changes DNS, or applies infrastructure from this
workflow.

## Git repository to runnable project

The Web Console now provides a governed end-to-end path:

1. Open `/repositories`, select GitHub, Gitee, or an allowlisted generic HTTPS
   Git provider, and enter a credential-free clone URL plus branch, tag, or
   exact commit.
2. Create the workspace. ELMOS resolves the advertised ref to an exact commit,
   fetches that commit, inventories the repository, and shows completeness
   blockers before enabling writes.
3. Read or edit UTF-8 files in the isolated workspace. Every update is
   optimistic-concurrency protected by the previously read SHA-256 digest.
4. Select **项目生成**, **跨语言转换**, or **Spring 现代化**. The browser
   carries only the opaque workspace UUID (and exact HEAD for Spring) to the
   chosen business line; no Git credential or repository content is placed in
   the URL.
5. In **导入需求来源**, optionally list up to eight repository-relative files,
   one per line. If the list is empty, ELMOS deterministically prefers README,
   `docs/**`, local/cloud deployment, configuration, tests, and then source
   files.
6. Select exact target stacks and run **解析并合并来源**. The server rechecks
   the same tenant and actor, `COMPLETE` workspace status, source commit,
   current file path, UTF-8 encoding, and SHA-256 digest. Each imported file is
   recorded as `repository-file` and included in the approval-bound source
   bundle hash.
7. Review the normalized entities, fields, rules, permissions, open questions,
   source provenance, persistence, authentication, and target versions. An
   unresolved question or incompatible production profile blocks approval.
8. Run **一键生成、验证并归档**. The runner generates only from the approved,
   hash-bound request, executes available real builds/tests/startup probes, and
   produces a ZIP plus content-addressed evidence. A missing exact toolchain is
   reported as `NOT_RUN`, never silently replaced.
9. Download the archive. Every generated workspace includes:
   `docs/LOCAL_RUN.md`, `docs/CLOUD_DEPLOYMENT.md`,
   `deploy/deployment-options.json`, locked dependencies, tests, health
   endpoints, Dockerfiles, CI, Kubernetes assets, traceability, source
   provenance, SBOM, and generation/verification manifests.

Project Generation imports selected files as untrusted requirements text.
Translation materializes only digest-verified source, documentation,
configuration, and test text below the configured read-only source root.
Spring materialization copies an immutable, exact-HEAD handoff into the shared
Snapshot root while excluding protected secret-shaped paths and recording the
exclusion list and manifest digest. Scripts,
workflows, lifecycle hooks, binaries, Terraform, Kubernetes, Helm, Docker, and
CI definitions from the source repository are not executed by ingestion.
Merge, cloud apply, DNS, database migration, and production traffic remain
separate authorized operations and stay `NOT_RUN`.

## Safety contract

- Clone URLs must be credential-free HTTPS. `file:` URLs exist only behind the
  disabled-by-default local development flag.
- GitHub and Gitee selections require the exact `github.com` and `gitee.com`
  hosts. Self-hosted services use `GENERIC_GIT` and must be present in the
  exact server-side host allowlist; wildcards are not accepted.
- Requested refs are resolved through advertised heads/tags and bound to an
  exact 40-character commit. The fetched commit must match.
- Symbolic links, non-regular files, binary data, secret-shaped files,
  `.git/**`, and `ownership/policy.json` are not editable. Secret-shaped files
  are also not readable or eligible as project-generation sources.
- Every changed path must be listed in `approvedPaths`. Existing files also
  require their previously read SHA-256 digest, preventing silent concurrent
  overwrite.
- A detected `CODEOWNERS` file requires explicit owner approval. Repositories
  with submodules or Git LFS declarations remain read-only until those objects
  receive separate authorization, hydration, and digest verification.
- Repository and file counts are bounded. Credentials are ephemeral and are
  neither written to Git configuration nor stored in workspace metadata.
- Total workspace count is bounded and expired workspaces are removed after
  the configured TTL; corrupt or unknown directories are never auto-deleted.
- Each API attempt and completion/failure is written to the tenant-isolated
  user activity log without repository content, clone URLs, file paths, or
  credentials.
- Commit requires the current exact HEAD and the complete set of pending paths;
  unapproved or protected paths fail closed. Push is non-force and succeeds
  only after the provider advertises the expected commit on the exact ELMOS
  branch. GitHub/Gitee PR publication stores a tenant-workspace-local
  idempotency receipt; a conflicting retry is rejected.

## Control-plane configuration

Set the following server-side values:

```text
ELMOS_REPOSITORY_WORKSPACE_ENABLED=true
ELMOS_REPOSITORY_WORKSPACE_API_KEY=<at least 24 characters>
ELMOS_REPOSITORY_WORKSPACE_ROOT=/absolute/bounded/workspace/path
ELMOS_REPOSITORY_CREDENTIAL_ROOT=/absolute/owner-only/credential/path
ELMOS_REPOSITORY_WORKSPACE_MAX_FILES=100000
ELMOS_REPOSITORY_WORKSPACE_MAX_BYTES=2147483648
ELMOS_REPOSITORY_ALLOWED_GENERIC_HOSTS=git.example.com,git.internal.example
ELMOS_REPOSITORY_WORKSPACE_MAX_COUNT=1000
ELMOS_REPOSITORY_WORKSPACE_TTL_HOURS=168
ELMOS_REPOSITORY_GITHUB_API_BASE=https://api.github.com
ELMOS_REPOSITORY_GITEE_API_BASE=https://gitee.com
ELMOS_SNAPSHOT_MATERIALIZED_ROOT=/absolute/shared/spring-materialized/path
```

The Web Console additionally needs:

```text
ELMOS_REPOSITORY_WORKSPACE_BASE_URL=https://control-plane.example
ELMOS_REPOSITORY_WORKSPACE_API_KEY=<same internal key>
ELMOS_REPOSITORY_WORKSPACE_TENANT_ID=<trusted tenant>
ELMOS_REPOSITORY_WORKSPACE_ACTOR_ID=<trusted actor>
ELMOS_REPOSITORY_WORKSPACE_USER_TOKEN=<browser/session gate, at least 24 characters>
```

To pass a repository workspace into Project Synthesis, the repository and
runner identities must be exactly equal:

```text
ELMOS_REPOSITORY_WORKSPACE_TENANT_ID == ELMOS_LOCAL_RUNNER_TENANT_ID
ELMOS_REPOSITORY_WORKSPACE_ACTOR_ID  == ELMOS_LOCAL_RUNNER_ACTOR_ID
```

The generation runner also requires the fail-closed configuration below:

```text
ELMOS_LOCAL_RUNNER_ENABLED=true
ELMOS_LOCAL_RUNNER_ROOT=/absolute/dedicated/non-repository/path
ELMOS_REPOSITORY_ROOT=/absolute/path/to/elmos
ELMOS_UV_PATH=/absolute/path/to/uv
ELMOS_LOCAL_RUNNER_AUTH_TOKEN=<24-4096 character short-lived token>
ELMOS_LOCAL_RUNNER_AUTH_TOKEN_EXPIRES_AT=<timezone-aware time within 24 hours>
ELMOS_LOCAL_RUNNER_TENANT_ID=<same trusted tenant>
ELMOS_LOCAL_RUNNER_ACTOR_ID=<same trusted actor>
ELMOS_LOCAL_RUNNER_EXECUTOR=ROOTLESS_CONTAINER
ELMOS_LOCAL_RUNNER_CONTAINER_ENGINE=/absolute/path/to/rootless/podman-or-docker
ELMOS_LOCAL_RUNNER_BUILD_NETWORK=none
```

`HOST_DEVELOPMENT` is accepted only for explicit non-production development.
Production refuses it. The runner root cannot be `/`, the repository root, or
an ancestor of the repository, and production execution requires a rootless
container engine with the repository mounted read-only and undeclared network
access denied.

The browser never receives the internal repository key or Git credential.
Production uses the encrypted `__Host-` enterprise session and the verified
OIDC access token. The explicit bearer-token field appears only in controlled
non-production mode.

## Local hardware and software

Sizing is conservative engineering guidance; the exact generated target list
in `/generation` and `deploy/deployment-options.json` is authoritative for a
specific project.

| Workload | Minimum | Recommended |
|---|---:|---:|
| Repository pull/read/edit only | 4 vCPU, 8 GB RAM, 20 GB free disk plus repository quota | 8 vCPU, 16 GB RAM, SSD free space at least twice the largest admitted repository |
| One target generated, built, tested, and started at a time | target-dependent; 2-4 vCPU, 2-8 GB RAM, 2-10 GB disk | up to 8 vCPU, 16 GB RAM, 20 GB disk for the heaviest current Rust/Kotlin target |
| All eight generated targets stored and verified sequentially | 8 vCPU, 16 GB RAM, 84 GB free disk | 12 vCPU, 24 GB RAM, 120 GB SSD |
| All eight targets built/run concurrently | 40 vCPU, 72 GB RAM, 84 GB free disk | dedicated runner; size from measured peak plus safety margin |

Required control-plane and Web Console software is Git, Java 21, Maven 3.9,
Node 26, pnpm 10.12.4, Python 3.12, uv, Make, curl, and a rootless Podman or
Docker engine for production execution. Generated target toolchains are exact:
Java 21/Spring Boot, Python 3.12/FastAPI, .NET 10/ASP.NET Core,
TypeScript 5.9/Node 26/NestJS, Go 1.25, Kotlin 2.2/JVM 21/Ktor, PHP 8.4, and
Rust 1.89/Axum. Install and verify repository-pinned toolchains with:

```bash
make project-synthesis-toolchains
make project-synthesis
make web
```

## Local startup

After configuring a PostgreSQL-backed control plane and the environment above,
start the two application surfaces in separate terminals:

```bash
# Terminal 1, repository root
mvn -pl apps/control-plane -am spring-boot:run

# Terminal 2, repository root
pnpm --dir apps/web-console install --frozen-lockfile
pnpm --dir apps/web-console dev
```

Then verify:

```bash
curl --fail http://127.0.0.1:8080/actuator/health
curl --fail http://127.0.0.1:3000/api/health?probe=readiness
```

Open `http://127.0.0.1:3000/repositories` and follow the nine-step workflow
above. If a generated target completes, extract the ZIP, read
`docs/LOCAL_RUN.md`, enter the selected target directory, run `make test`, then
`make run`, and verify its declared `/health` endpoint. Do not continue after
a failed test, unavailable toolchain, digest mismatch, incomplete submodule/LFS
workspace, or blocked readiness probe.

## Cloud deployment handoff

The generated project recommends Google Cloud Run for stateless HTTP services
and lists Azure Container Apps, AWS ECS on Fargate, and managed Kubernetes as
conditional alternatives. The generated `docs/CLOUD_DEPLOYMENT.md` provides
the exact target port, Dockerfile, health path, required account/region/billing
decisions, least-privilege service identity, immutable image digest, fixed
Secret versions, capacity settings, database/authentication inputs, validation,
rollback, and cleanup steps.

Cloud deployment is deliberately not automatic from repository ingestion.
Before an authorized operator applies anything:

1. pass all local target tests and startup probes;
2. build and scan the non-root image;
3. push it to the approved registry and resolve `image@sha256:...`;
4. create a dedicated runtime identity with only required roles;
5. mount secrets from the provider secret service and pin versions;
6. configure private ingress by default, CPU/RAM/concurrency/min/max instances,
   health behavior, budgets, alerts, logs, database connection limits, backup,
   restore, and rollback owners;
7. deploy an immutable revision, run health, negative authentication,
   tenant-isolation, CRUD, restart, and rollback checks;
8. preserve revision/configuration/log evidence and independently accept it;
9. remove failed revisions, unused images/secrets, temporary databases, DNS,
   and networking, then reconcile the final bill.

Official references used by this handoff are
[GitHub cloning](https://docs.github.com/en/repositories/creating-and-managing-repositories/cloning-a-repository),
[Gitee HTTPS cloning](https://gitee.com/help/articles/4111),
[Cloud Run container deployment](https://docs.cloud.google.com/run/docs/deploying),
and [Cloud Run secret configuration](https://docs.cloud.google.com/run/docs/configuring/services/secrets).

## Private repositories

A request may refer to a server-side credential by a safe identifier such as
`customer-a-gitee`. The credential root then contains
`customer-a-gitee.credential`, owned and readable only by the service account:

```text
git-username
2026-07-28T12:00:00Z
provider-token-or-password
```

Never commit this file, put the token in a clone URL, or expose the reference
directory through the Web Console. Credential files are read per operation,
copied into an `EphemeralCredential`, cleared after JGit returns, and never
persisted in the workspace. The expiry must be in the future and no more than
one hour from lease time.

## API surface

All control-plane calls require the internal repository key plus trusted
organization and actor headers.

- `GET /api/v1/repository-workspaces/capabilities`
- `POST /api/v1/repository-workspaces`
- `GET /api/v1/repository-workspaces/{workspaceId}`
- `GET /api/v1/repository-workspaces/{workspaceId}/files?path=...`
- `POST /api/v1/repository-workspaces/{workspaceId}/changes`
- `POST /api/v1/repository-workspaces/{workspaceId}/commit`
- `POST /api/v1/repository-workspaces/{workspaceId}/push`
- `POST /api/v1/repository-workspaces/{workspaceId}/pull-request`
- `POST /api/v1/repository-workspaces/{workspaceId}/materializations/spring`
- `DELETE /api/v1/repository-workspaces/{workspaceId}`

An apply request is explicit:

```json
{
  "baseCommit": "40-character source commit",
  "intent": "Human-readable requested change",
  "codeOwnerApproval": false,
  "approvedPaths": ["README.md"],
  "changes": [
    {
      "operation": "UPSERT",
      "path": "README.md",
      "expectedSha256": "digest returned by the read endpoint",
      "contentBase64": "base64-encoded UTF-8 text"
    }
  ]
}
```

The local-change result exposes `pushed=false`,
`pullRequestCreated=false`, and `deployed=false`. Workspace inspection
separately exposes `currentHeadCommit`, `pendingPaths`, `pushedCommit`,
`pullRequestId`, and `pullRequestUrl`, so refresh/recovery cannot confuse local,
remote-branch, PR, merge, or deployment state.

The Web Console displays the opaque workspace UUID and provides an
identity-bound recovery field. Refreshing the browser does not persist a Git
credential or browser token; the user re-enters the short-lived token and
recovers the UUID, while the control plane rechecks both tenant and actor.
