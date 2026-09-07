---
name: elmos-generation-journey-closure
description: Implement and verify the governed ELMOS Project Synthesis journey across Web Console, capability contracts, CLI commands and the Python engine. Use when changing the multilingual project generation UI, target profiles, Draft-Approve-Generate-Verify workflow, generated command handoff, generation status, or Java/Python/C# starter capability boundaries.
---

# ELMOS Generation Journey Closure

## Objective

Keep the multilingual generation experience useful and honest from project intent through verified starter output. The Web Console may prepare and hand off commands, but it must never bypass approval, execute hidden host commands, or present generation, verification, delivery or certification as completed when they did not run.

## Authoritative sources

Inspect these before editing:

- `engines/project-synthesis-engine/README.md`
- `engines/project-synthesis-engine/src/elmos_project_synthesis/cli.py`
- `engines/project-synthesis-engine/src/elmos_project_synthesis/intake.py`
- `engines/project-synthesis-engine/src/elmos_project_synthesis/models.py`
- `engines/project-synthesis-engine/src/elmos_project_synthesis/workspace.py`
- `engines/project-synthesis-engine/src/elmos_project_synthesis/verification.py`
- `apps/web-console/app/generation/`
- `apps/web-console/app/lib/contracts.ts`
- `apps/web-console/app/lib/catalog.ts`

The engine contract outranks copied UI text.

## Exact state machine

```text
DRAFT
→ REVIEW_REQUIRED
→ APPROVED (actor, UTC timestamp and payload digest bound)
→ GENERATED (new or engine-owned workspace only)
→ VERIFIED or FAILED/BLOCKED
```

Production delivery remains `NOT_RUN` and certification remains `NOT_CERTIFIED` unless their separate governed workflows actually execute.

## UI requirements

1. Collect project name, namespace, description, core entity and one or more exact targets.
2. Distinguish current editable values from a submitted local preview.
3. Validate missing, malformed, empty and no-target states without uploading customer content.
4. Disclose whether capabilities came from a live API or repository contract.
5. Show exact target language, runtime, framework and port values from one shared catalog.
6. Generate the complete terminal handoff:
   - create draft;
   - review and approve with a named actor;
   - generate to a bounded project directory;
   - run real verification and write evidence.
7. Use commands that match the documented execution environment, including `uv run elmos-project-synthesis`.
8. Provide accessible copy actions, live feedback, labels, descriptions, error relationships and keyboard-operable controls.
9. Never run a generated command in the browser or Next.js process.

## Capability contract

Expose a typed `/api/capabilities/generation` response containing:

- source and fetch time;
- engine schema/version boundary;
- supported exact targets;
- ordered workflow stages;
- generation, external execution, production delivery and certification states;
- limitations and user-facing note.

When no generation service exists, return `REPOSITORY_CONTRACT`; do not label static metadata `LIVE_API`.

## Command contract

Build commands from validated values using shell-safe quoting. Keep file handoff explicit:

```text
synthesis-request.json
→ approved-request.json
→ generated/<project-name>
→ verification.json
```

Do not interpolate a path that can escape the intended generated directory. Do not include secrets, tokens, customer code or production data.

## Engine invariants

- Approval fails when open questions remain.
- Approval binds the reviewed payload digest and actor.
- Generation rejects modified approvals, unsafe output paths, unmanaged non-empty directories and modified managed files.
- Verification invokes only selected native toolchains and reports missing tools or failed probes as non-success.
- The starter scope remains single-entity, in-memory CRUD unless the authoritative engine contract changes with tests.

## Required checks

Run:

```bash
pnpm --dir apps/web-console check
make project-synthesis
make production-readiness-check
```

Also verify the generated UI command sequence against the CLI parser options and order. Exercise at least Java, Python and C# target selection, no-target rejection, unsafe name rejection, clipboard failure feedback, repository-contract fallback and exact status disclosure.

## Evidence boundary

A successful Next.js build proves only the UI compiles. A successful engine acceptance run can prove generation, target builds, tests and startup probes for its temporary fixtures. Neither proves identity, tenancy, persistent storage, cloud deployment, SLO, DR, customer acceptance or certification.

## Completion criteria

- One shared target catalog drives UI and capability API.
- The four-stage command handoff is complete and executable in the documented engine environment.
- UI source and status labels match actual execution.
- The engine acceptance run generates, builds, tests and probes every selected supported target.
- All unavailable external evidence remains explicitly non-success.
