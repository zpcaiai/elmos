# Generation workload image

This directory builds the container the runner-agent executes for hosted
`GENERATION` / `project-synthesis` jobs. It is the missing piece behind
`ELMOS_RUNNER_IMAGE_GENERATION`: the control plane fail-closes with
`ELMOS_RUNNER_IMAGE_NOT_CONFIGURED` until a **digest-pinned** reference to
this image is configured.

## Contract

| Side | Fixed by | This image provides |
|---|---|---|
| Input | `/elmos/in` (read-only) with `request.json`, `checkpoint.json` | reads `actor` + `synthesisRequest` from the payload |
| Output | `/elmos/out` (read-write) | `generated-project.zip` (PROJECT_ARCHIVE), `evidence/*` (EVIDENCE_PACK), `logs/pipeline.log` (BUILD_LOG) |
| Progress | stdout line `::elmos stage=<s> progress=<n>` | `pipeline 10 → archiving 90 → complete 100` (or `blocked 100`) |
| Exit | 0 = archive produced and verified-by-engine | 0 only for pipeline `PASSED`/`PARTIAL` with a non-empty archive |
| Sandbox | read-only root, `--network=none`, non-root, tmpfs `/tmp` | pure-stdlib engine, no writes outside `/elmos/tmp` and `/elmos/out` |

The payload is written by `apps/web-console/app/lib/server/hostedExecutionClient.ts`
(`createHostedGenerationJob`) and carries the same `synthesisRequest` the
local runner persists as `synthesis-request.json`, plus the identical
project-intent document, so local and hosted jobs run the identical engine
pipeline.

## Build

```bash
python3 scripts/operations/build_generation_workload_image.py
# or manually:
docker build -t elmos-generation-workload:$(grep -m1 '^version' engines/project-synthesis-engine/pyproject.toml | cut -d'"' -f2) engines/project-synthesis-engine/workload
```

The build script also supports `--smoke`, which runs the image once under
the runner-agent sandbox flags (`--network=none`, `--read-only`, non-root)
with a fixture request and asserts the archive and progress lines appear.

After building, pin it:

```bash
docker build --iidfile <(echo) ...   # or:
docker inspect --format '{{.Id}}' elmos-generation-workload:<version>
# then set on the control plane deployment:
ELMOS_RUNNER_IMAGE_GENERATION=<registry>/elmos-generation-workload@sha256:<digest>
```

Only a digest reference (`name@sha256:…`) is accepted - by the control
plane *and* again by `ContainerRuntime.validateImage` on the runner node.

## Verification toolchain boundary

The default image contains the engine only. Verification for a generated
target needs that target's pinned toolchain; when absent, the engine keeps
the target `NOT_RUN` and the pipeline result is `PARTIAL` (never faked).
A toolchain-complete variant must be built from the pinned upstream images
in `src/elmos_project_synthesis/container_images.py` on a build machine
that is allowed to pull them; verification must never be weakened to make
the default image report more than it can prove.

## Local (docker-free) test

The entrypoint is plain Python and is covered by the engine test suite:

```bash
cd engines/project-synthesis-engine
uv run --offline pytest tests/test_workload_entrypoint.py
```

The test exercises the success path (`PARTIAL` without toolchains, archive
+ evidence published, progress lines emitted) and every fail-closed path
(malformed payload, rejected pipeline status, missing archive).
