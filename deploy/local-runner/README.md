# Governed local generation Runner

This profile runs the Web Console beside the repository toolchains so the
Generation page can analyze, generate, verify, download, start, health-check,
and stop a project without granting arbitrary shell access.

## Secure configuration

1. Copy `runner.env.example` to an owner-only file outside the repository.
2. Create a random token of at least 24 characters in a separate owner-only
   file (`chmod 600`). Configure its absolute path with
   `ELMOS_LOCAL_RUNNER_AUTH_TOKEN_FILE`; do not configure the inline token at
   the same time. Bind the lease with
   `ELMOS_LOCAL_RUNNER_AUTH_TOKEN_EXPIRES_AT`; it must include a timezone, be
   in the future, and be no more than 24 hours away.
3. Use a dedicated absolute state directory that is neither the repository nor
   one of its ancestors. The Runner creates tenant/job files with owner-only
   permissions and never stores the bearer token in jobs, logs, or artifacts.
4. Load the environment, run `pnpm --dir apps/web-console check`, then run
   `pnpm --dir apps/web-console start`. Readiness is available at
   `/api/health?probe=readiness`; liveness is
   `/api/health?probe=liveness`.
5. Production mode requires `ELMOS_LOCAL_RUNNER_EXECUTOR=ROOTLESS_CONTAINER`
   and an absolute rootless Podman or Docker executable. Startup preflight
   verifies rootless mode. `HOST_DEVELOPMENT` is an explicit local-only escape
   hatch and is rejected whenever `NODE_ENV=production`.

The containerized shared Web Console keeps the local Runner disabled. It is a
separate security boundary and must not mount a repository, host toolchains, or
the Runner token.

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
fixed per-language shapes, fixed ports, and service-identity health checks.
The production executor builds and starts only generated Dockerfiles with a
rootless engine, a read-only runtime filesystem, dropped capabilities,
`no-new-privileges`, PID/CPU/memory limits, and no runtime network. Build
network access defaults to `none`; rootless Podman may explicitly select
`slirp4netns`. Docker build egress requires a pre-created exact network carrying
both `io.elmos.network-purpose=approved-build-egress` and
`io.elmos.approved=true`. The running service is attached only to a per-job
internal network and published on `127.0.0.1`, so it has no external egress.

The Python production profile emits PostgreSQL migrations, forced tenant RLS,
default-deny JWT/OIDC authorization, file-based secret references, metrics,
SLO/alert contracts, and backup/restore runbooks. Real provider provisioning,
secret delivery, migration execution, deployment, restore drills, independent
review, and production certification remain `NOT_RUN` until their exact
authorized evidence exists.

Jobs are persisted atomically before dispatch. After a process restart,
unfinished jobs are requeued at most twice and then fail closed for manual
review. Rootless container state is reconciled on job reads and readiness
checks; active container state is never inferred from an old PID.

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
