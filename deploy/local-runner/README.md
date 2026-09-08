# Governed local generation Runner

This profile runs the Web Console beside the repository toolchains so the
Generation page can analyze, generate, verify, download, start, health-check,
and stop a project without granting arbitrary shell access.

## Secure configuration

1. Copy `runner.env.example` to an owner-only file outside the repository.
2. Create an issuer/verifier signing key of at least 32 random bytes in a
   separate owner-only file (`chmod 600`) and configure its absolute path and
   rotation identifier with `ELMOS_LOCAL_RUNNER_AUTH_SIGNING_KEY_FILE` and
   `ELMOS_LOCAL_RUNNER_AUTH_KEY_ID`. Production rejects the legacy inline and
   file-backed static bearer. The trusted local controller must issue a one-use
   HS256 credential lasting at most 300 seconds, with exact issuer, audience,
   tenant, actor, permission, HTTP method, request path, key id, and `jti`
   bindings. Replays fail closed. `ELMOS_LOCAL_RUNNER_AUTH_TOKEN_EXPIRES_AT`
   bounds the signing-key authorization lease: startup requires a timezone and
   at least five minutes remaining, and refuses a lease over 24 hours.
   The repository-owned issuer is `issue_service_credential.py`; invoke it only
   from the trusted local controller and pass the exact tenant, actor,
   permission, method, and `/api/generation/...` path for one request.
3. Install the immutable repository at `/opt/elmos` and use the dedicated
   `/var/lib/elmos-generation-runner` state directory. Both systemd units bind
   `/opt/elmos` read-only and permit writes only to the state root. The startup
   preflight recursively rejects any repository entry writable by the service
   UID and rejects service-replaceable or hard-linked `uv`, `pnpm`, or
   container-engine paths. Each executable must also match its owner-supplied
   SHA-256 (`ELMOS_UV_SHA256`, `ELMOS_LOCAL_RUNNER_PNPM_SHA256`, and
   `ELMOS_LOCAL_RUNNER_CONTAINER_ENGINE_SHA256`).
   The state directory must be neither the repository nor
   one of its ancestors. The Runner creates tenant/job files with owner-only
   permissions and never stores credentials or signing keys in jobs, logs, or artifacts.
4. Store the environment as `/etc/elmos/generation-runner.env`, owned by root
   and mode `0600`. Keep both `ELMOS_LOCAL_RUNNER_ROOT` and the repository on a
   persistent filesystem; `/tmp`, an ephemeral container layer, and a network
   share are not supported production state roots.
   The Web Console and reaper both derive the engine `HOME` from the canonical
   `$ELMOS_LOCAL_RUNNER_ROOT/home` directory and require it to be owner-only.
   If the rootless engine needs an XDG runtime directory, configure its
   canonical owner-only absolute path as
   `ELMOS_LOCAL_RUNNER_ENGINE_XDG_RUNTIME_DIR`; ambient `XDG_RUNTIME_DIR` is not
   inherited. Rootless Docker additionally requires
   `ELMOS_LOCAL_RUNNER_DOCKER_UNIX_SOCKET` to be an absolute live Unix-domain
   socket owned by the service user. Give the filesystem path only, not a
   `unix://` URI. TCP, HTTP, SSH, relative, symlinked, and non-socket endpoints
   fail closed.
5. Set `ELMOS_LOCAL_RUNNER_SERVICE_UID` to the numeric, non-root UID of the
   fixed `elmos-runner` account and set `ELMOS_LOCAL_RUNNER_PNPM_PATH` to an
   absolute executable. Install the independent lease reaper and Runner units.
   Both units run as the same `elmos-runner` user/group and execute the
   repository-owned production preflight before startup:

   ```bash
   sudo install -o root -g root -m 0644 \
     deploy/local-runner/systemd/elmos-generation-runtime-reaper.service \
     /etc/systemd/system/elmos-generation-runtime-reaper.service
   sudo install -o root -g root -m 0644 \
     deploy/local-runner/systemd/elmos-generation-runner.service \
     /etc/systemd/system/elmos-generation-runner.service
   sudo systemctl daemon-reload
   sudo systemctl enable --now elmos-generation-runtime-reaper.service \
     elmos-generation-runner.service
   sudo systemctl is-active elmos-generation-runtime-reaper.service
   sudo systemctl is-active elmos-generation-runner.service
   sudo systemctl show -p User,Group,EnvironmentFiles,CPUQuotaPerSecUSec,MemoryMax,TasksMax \
     elmos-generation-runtime-reaper.service elmos-generation-runner.service
   ```

   Verify that `$ELMOS_LOCAL_RUNNER_ROOT/.runtime-reaper-heartbeat.json` is
   owner-only, uses schema `elmos.generation-runtime-reaper-heartbeat.v2`, and
   reports `REAPER_IDLE` or `REAPER_SWEEP_COMPLETE`. Its
   `engine_context_sha256` binds the exact engine executable, canonical HOME,
   optional XDG runtime directory, and Docker socket; the Web Console rejects
   a fresh heartbeat produced for a different context. Production start fails
   closed as `RUNTIME_REAPER_NOT_READY` when this heartbeat is missing, blocked,
   or stale.
6. Run `python3 deploy/local-runner/validate_production_contract.py` for the
   digest-bound static contract and `pnpm --dir apps/web-console check`. The
   systemd units then perform the live UID/path/ownership preflight. Readiness
   is available at `/api/health?probe=readiness`; liveness is
   `/api/health?probe=liveness`.
7. Production mode requires `ELMOS_LOCAL_RUNNER_EXECUTOR=ROOTLESS_CONTAINER`
   and an absolute rootless Podman or Docker executable. Startup preflight
   verifies rootless mode. `HOST_DEVELOPMENT` is an explicit local-only escape
   hatch and is rejected whenever `NODE_ENV=production`.

The containerized shared Web Console keeps the local Runner disabled. It is a
separate security boundary and must not mount a repository, host toolchains, or
the Runner signing key.

## Supported workflow and limits

The bundled matrix has eight API emitters. Java, Python, and C# are `limited`;
TypeScript, Go, Kotlin, PHP, and Rust remain `experimental` until their
independent representative evidence closes. All eight support the exact
in-memory plus `auth=none` starter. Python additionally supports the exact
PostgreSQL 17.5 plus JWT/OIDC production profile. Natural-language descriptions may use
`实体`, `<entity>字段`, `关系`, `规则`, and `权限` markers; the review screen
shows the parsed entities, fields, relationships, rules, permission statements,
acceptance criteria, and blocking questions before approval.

Each selected target is built and tested with its declared exact toolchain.
One-click start is offered only after that target's startup probe passed and the
generated workspace still matches its content digests. Runtime commands have
fixed per-language shapes, dynamically assigned loopback-only host ports, and
service-identity health checks. The 600-second lease starts only after the
identity/readiness probe succeeds; build and cold-start time do not consume the
browser's usable preview window.
Before building, the Runner validates the rootless engine, the exact build
network policy, every digest-pinned `FROM` image, and the local image cache.
With the default `none` build network, an uncached image fails immediately as
`TOOLCHAIN_IMAGES_NOT_AVAILABLE_OFFLINE`. With an approved build network, the
diagnostic reports `APPROVED_BUILD_EGRESS_REQUIRED` before the immutable image
is pulled. This keeps first-run setup, network approval, and runtime isolation
as separate, actionable states.
The production executor builds and starts only generated Dockerfiles with a
rootless engine, a read-only runtime filesystem, dropped capabilities,
`no-new-privileges`, PID/CPU/memory limits, and no runtime network. Build
network access defaults to `none`; rootless Podman may explicitly select
`slirp4netns`. Docker build egress requires a pre-created exact network carrying
both `io.elmos.network-purpose=approved-build-egress` and
`io.elmos.approved=true`. The running service is attached only to a per-job
internal network and published on `127.0.0.1`, so it has no external egress.

Repository tests cover canonical-path validation, TCP rejection, Unix-socket
mapping, sanitized helper environments, and the heartbeat context binding.
The production contract additionally binds the exact rootless helper and
reaper digests, fixed systemd service identity, capability bounding, restart
limits, stop escalation window, service resource ceilings, default-deny build
network, tenant scan bounds, and backup-bound retained-job GC. The reaper has
an explicit systemd IP deny with loopback as its only IP exception; job
containers retain the stronger per-job internal/no-external-egress contract.
Execution against a real Linux systemd service and a real rootless Docker
daemon/socket remains `NOT_RUN` until performed under the target service UID;
production Docker configuration therefore fails closed when the explicit Unix
socket is absent or cannot be verified.

The Python production profile emits PostgreSQL migrations, forced tenant RLS,
default-deny JWT/OIDC authorization, file-based secret references, metrics,
SLO/alert contracts, and backup/restore runbooks. Real provider provisioning,
secret delivery, migration execution, deployment, restore drills, independent
review, and production certification remain `NOT_RUN` until their exact
authorized evidence exists.

Jobs are persisted atomically before dispatch. After a process restart,
unfinished jobs are requeued at most twice and then fail closed for manual
review. Rootless container state is reconciled on job reads and readiness
checks, by a per-lease watchdog, and by the independent reaper; active
container state is never inferred from an old PID. The contract is a complete
600-second usable lease followed by immediate verified cleanup attempts.
Scheduler and engine latency mean this is not a claim that every resource
disappears at exactly 600.000 seconds.

## Backup and recovery

Backups are offline and fail closed. First quiesce the Runner, stop or drain all
active jobs and runtimes, then create and verify the content-addressed archive:

```bash
python3 scripts/operations/generation_runner_backup.py quiesce \
  --root "$ELMOS_LOCAL_RUNNER_ROOT" --actor "$ELMOS_LOCAL_RUNNER_ACTOR_ID"
python3 scripts/operations/generation_runner_backup.py backup \
  --root "$ELMOS_LOCAL_RUNNER_ROOT" --actor "$ELMOS_LOCAL_RUNNER_ACTOR_ID" \
  --output /absolute/backup/elmos-runner-backup.zip
python3 scripts/operations/generation_runner_backup.py verify \
  --archive /absolute/backup/elmos-runner-backup.zip
```

Restore always targets a nonexistent directory, verifies every declared byte,
rejects path traversal, and remains quiesced until the same authorized actor
explicitly resumes it:

```bash
python3 scripts/operations/generation_runner_backup.py restore \
  --archive /absolute/backup/elmos-runner-backup.zip \
  --destination /absolute/path/to/restored-runner \
  --actor "$ELMOS_LOCAL_RUNNER_ACTOR_ID"
python3 scripts/operations/generation_runner_backup.py resume \
  --root /absolute/path/to/restored-runner \
  --actor "$ELMOS_LOCAL_RUNNER_ACTOR_ID"
```

Copy the archive to independently managed encrypted storage and perform a
scheduled restore drill. Repository tests prove the local archive contract;
production RPO/RTO, off-host retention, alerting, and disaster recovery remain
`NOT_RUN` until executed in the authorized operating environment.

## Backup-bound retention and storage GC

Job admission reserves capacity for every non-terminal job and enforces the
configured per-tenant job and byte limits. Physical deletion is deliberately an
offline operator action: no Web request is allowed to recursively delete a job.
After quiescing and creating the archive above, first inspect the exact plan,
then apply it with the same immutable archive and rootless engine identity:

```bash
python3 scripts/operations/generation_runner_backup.py gc \
  --root "$ELMOS_LOCAL_RUNNER_ROOT" \
  --tenant "$ELMOS_LOCAL_RUNNER_TENANT_ID" \
  --actor "$ELMOS_LOCAL_RUNNER_ACTOR_ID" --max-jobs 25
python3 scripts/operations/generation_runner_backup.py gc \
  --root "$ELMOS_LOCAL_RUNNER_ROOT" \
  --tenant "$ELMOS_LOCAL_RUNNER_TENANT_ID" \
  --actor "$ELMOS_LOCAL_RUNNER_ACTOR_ID" --max-jobs 25 --apply \
  --backup-archive /absolute/backup/elmos-runner-backup.zip \
  --repository-root "$ELMOS_REPOSITORY_ROOT" \
  --engine "$ELMOS_LOCAL_RUNNER_CONTAINER_ENGINE"
python3 scripts/operations/generation_runner_backup.py resume \
  --root "$ELMOS_LOCAL_RUNNER_ROOT" --actor "$ELMOS_LOCAL_RUNNER_ACTOR_ID"
```

Only terminal jobs whose persisted retention deadline has passed and whose
`legalHold` value is exactly `false` are candidates. Apply verifies that every
candidate byte is present in the actor/maintenance-bound backup, cleans exact
lease rootless resources, moves the job to confined trash, and records each
state transition before verified purge. If apply is interrupted, keep the
Runner quiesced and rerun the same command with the same archive; `resume` fails
closed while a GC receipt still needs recovery.

Do not automate this sequence until the Linux service account, immutable
off-host archive retention, alerting, restore drill, and interruption recovery
have been exercised in the target environment. Those production operations and
an authorized Legal Hold set/release workflow remain `NOT_RUN`; the checked-in
boolean is only a fail-closed deletion filter, not a commercial records-hold
control plane.
