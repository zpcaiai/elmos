# FRT G01-G30 platform integration

Exact integration pack for `FRT_G01_G30_Complete_Skills_Pack@1.0.0` into `ELMOS_FRONTEND_CLIENT@1.2.0` and the ELMOS Next.js Web Console.

The pack covers immutable installation, the typed shared Runtime, 30-Batch/472-Skill discovery, the 30 directed frontend routes, API/CLI/UI surfaces, local tests, and fail-closed evidence boundaries.

Every generated route carries a target-specific runnable contract. After building
`engines/frontend-client-engine`, materialize a create-only deliverable with:

```sh
node scripts/frt/materialize_frt_route.mjs --request route-request.json --output generated-route
```

The exact request fields are `source`, `target`, and bounded `files`. The command
generates through typed UI IR, attaches and validates the portable Batch 46 pack,
and publishes the output atomically. The recipient then runs `./run-smoke.sh`;
only `smoke/tools/run_smoke_gate.py` may declare that generated artifact
`runnable`. A missing native toolchain returns `NOT_RUN`, never a fabricated pass.

External qualification is executable through `scripts/frt/external_evidence.py` and `acceptance/external-evidence-profile.json`. The workflow requires a signed run authorization, a separately configured external Runner, exact evidence roles and metrics, DLP-safe content-addressed artifacts, and three Ed25519 signatures from the executor, an independent verifier, and the accountable approver. Repository content never selects a shell command.

Visual candidates and approved baselines are physically separate. The strict Playwright quality config uses `updateSnapshots=none`; missing or changed approved baselines fail rather than being regenerated. Physical-device inventory is privacy minimized and never substitutes for install/launch, P0 journeys, visual review, assistive technology or customer acceptance.

These implementations make the external gates runnable; they do not claim that real customer repositories, independent holdout, physical-device/manual accessibility, proof, representative performance, penetration, DR, production or customer campaigns have run.
