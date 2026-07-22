# Batch 14 verification: Frontend and Client Modernization Engine

Verified on macOS on 2026-07-21. This report separates repository implementation from customer rendering, device, publishing, and production evidence.

## Repository-complete scope

- `engines/frontend-client-engine` is an independently runnable TypeScript/Node worker using the shared `/engine/v1` API. Static analysis never installs packages, imports customer modules, starts a development server, or executes package scripts.
- Workspace discovery recognizes npm, Yarn, pnpm, Bower, legacy/modern builders, Web, Electron, Android, iOS, browser targets, tests, entry points, multi-lock conflicts, and client-exposed secret-like environment names.
- UI analysis separates routes, components, state, events, permissions, API calls, dynamic dependencies, and unsafe HTML findings with Snapshot-bound Evidence.
- Planning separates behavior preservation, design-system adoption, UX redesign, and replatforming; it stages Angular majors, Vue compatibility removal, React classification, jQuery Migrate removal, quality gates, canary, and compatibility removal.
- Quality policy covers stable visual environments, approved target-design baselines, automated/manual accessibility separation, Electron IPC, desktop device feasibility, active mobile compatibility, offline idempotency, deep links, service workers, BFF boundaries, design mappings, and coordinated cutover.
- Java routes `FRONTEND_CLIENT` as the fourth engine, includes client/BFF/design/journey portfolio edges, and evaluates release progression without executing clients.
- Flyway V14 adds 71 tenant-scoped frontend/client tables with forced RLS and 14 append-only result/decision triggers.
- Six Draft 2020-12 JSON Schemas, six fixtures, an OpenAPI 3.1 contract, F001–F017 Skills, and 22 executable acceptance scenarios are present.

## Local verification

| Gate | Result |
|---|---|
| Frontend Client Engine | TypeScript strict build and 34 Node tests passed: all 22 required scenarios plus lifecycle, approval, static Evidence, idempotency, fail-closed execution/validation, UI graph, six Schema fixtures, scenario manifest, HTTP capability/fail-closed/conflict/tenant-boundary checks. |
| Java/Maven reactor | Full `clean verify` produced 62 Surefire reports containing 260 tests, 0 failures, 0 errors, and 1 Docker-dependent skip. |
| PostgreSQL 17 | V1–V14 applied in order to a fresh database: 668 public tables, 667 tenant-isolation policies, 668 `organization_id` columns, and 45 append-only trigger objects. |
| PostgreSQL isolation | A non-owner role scoped to each of two organizations saw exactly its own one client record; an update to `visual_differences` was rejected by the append-only trigger. |
| Skills | F001–F017 passed `quick_validate.py`; all 17 `agents/openai.yaml` manifests parsed, with no TODO/TBD/placeholder marker. Inventory is now 35 Build and 118 Runtime Skills. |
| Contracts | Six Draft 2020-12 Schemas, six fixtures, the Batch 14 scenario/policy documents, and the OpenAPI 3.1 YAML parsed; executable fixture checks passed in the TypeScript suite. |
| Web console | TypeScript and Next.js 16.2.10 production build passed; `/` and `/_not-found` were statically generated. |
| .NET regression | 12 tests passed and `dotnet format --verify-no-changes` passed. |
| Python regression | 31 tests passed; Ruff and strict mypy passed across 19 source files. |

The sole Maven skip is the Testcontainers Flyway test because no Docker API was available. It was not counted as success; the direct PostgreSQL execution above supplied current SQL, RLS, and append-only evidence instead. The temporary database was stopped and moved to macOS Trash for recoverable cleanup.

## Fail-closed external gates

The following remain `NOT_BUILT`, `UNAPPROVED`, `NOT_CONFIGURED`, `NOT_RUN`, or `BLOCKED` until authorized evidence exists:

1. Build, sign, scan, attest, and approve Web Legacy, Modern Web, Browser Matrix, Desktop Windows/macOS, Android, and iOS Runner profiles.
2. Reproduce real customer installs/builds and capture stable browser/font/OS/viewport/device visual baselines with approved privacy-safe test identities and fixtures.
3. Run keyboard, focus, NVDA/JAWS/VoiceOver/TalkBack, zoom/reflow, touch, high-contrast, real-device, and user validation; automated zero violations remains insufficient.
4. Execute real Angular/Vue/React/jQuery codemods and validate build, component, route, form, auth, API, visual, accessibility, performance, security, and journey behavior in fresh environments.
5. Exercise desktop IPC/native devices/local-data/installers/updates and mobile permissions/offline/push/deep-links/background/store candidates without production signing or automatic publication.
6. Validate every active Web/desktop/mobile/BFF/backend version combination, CDN/service-worker skew, canary cohorts, rollback, stability, usage, forced-upgrade approval, and decommission.

No static scan, fixture, schema, unit test, generated plan, or synthetic screenshot decision proves that a customer client rendered successfully or was released.
