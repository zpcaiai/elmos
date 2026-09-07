# Batch 22 verification

## Repository-complete scope

Batch 22 adds the independent `ELMOS_SOFTWARE_DELIVERY_PLATFORM` Java 21 Worker on port 8096, its exact `/engine/v1` API, 18 initialized Runtime Skills, five Draft 2020-12 schemas, 36 fail-closed acceptance scenarios, OpenAPI 3.1, five rootless Runner policies, fourteen `NOT_CONFIGURED` adapters, V28 with 81 tenant projections, Compose packaging, unified routing and independent control-plane adjudication.

The platform state model covers discovery, value-stream baselining, SCM planning, capability design, Golden Path construction, pipeline and artifact governance, environment automation, portal integration, pilot/cohort migration, measurement and continuous improvement. Production Repository deletion, history rewrite, Tag or Artifact deletion, protected-branch modification, automatic production deployment, platform-exception approval and forced Golden Path adoption remain prohibited.

## Evidence boundary

Repository tests prove contracts, policy ordering, tenant isolation, idempotency and default denial. GitHub, GitLab, Azure DevOps, Bitbucket, SVN, Perforce, ClearCase, Jenkins, Tekton, Artifact Registry, Backstage, CDEvents, GitOps and survey execution are `NOT_CONFIGURED` / `NOT_RUN`. No customer SCM estate, pipeline, artifact, environment, DORA observation, production promotion or platform adoption has been executed or certified.

## Verification status

- Engine and shared evidence-core tests: passed locally on 2026-07-22.
- 18 Skills: `quick_validate.py` passed; `agents/openai.yaml` prompts reference their Skill names.
- 36 scenarios, five schemas, fixture matrix, OpenAPI and Runner policy files: parsed locally.
- V28 static tenant/RLS contract: passed. Fresh PostgreSQL execution remains `NOT_RUN` because Docker is unavailable in this run.
- The packaged JAR served real localhost health, capabilities and fail-closed discovery responses on port 8096; the process was stopped after the check. Provider and production behavior remain external.
- The closing Maven reactor, web-console and Compose results are recorded in `batch-22-26-verification.md`.
