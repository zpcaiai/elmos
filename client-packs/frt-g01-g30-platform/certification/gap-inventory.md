# FRT G01-G30 gap inventory

## Locally implemented and verified

- Exact JSON contracts plus fail-closed Ed25519 identity, prerequisite certificate and content-addressed evidence verification.
- Repository gate results bind the exact current gate-request bytes and verify their own canonical digest; a copied stale READY result is rejected by the Batch 32 gate.
- 472 distinct, content-digested compiled execution contracts across 23 typed handler kinds and 2,832 exact contract/runtime/control-plane/Web/Admin/test surface manifests.
- Atomic exact organization/tenant/workspace/project/account/environment/release-scoped run storage, resource-scoped idempotency, optimistic versions, restart recovery and claim/heartbeat/cancel/retry/complete audit lifecycle.
- All five original per-Skill HTTP operations are implemented through the shared control plane; the Web BFF recomputes typed-input snapshot digests before signing, and subject verification binds exact Skill, run, result digest and source snapshot.
- Authenticated Web BFF and contract-aware plan/analyze/execute/verify UX accept every handler family's declared input, with artifact, Finding, Evidence and audit views.
- All 30 bounded directed routes generate through typed UI Interaction IR. React, Vue 3, Vue 2, WeChat Mini Program, ArkUI and Flutter source adapters derive the supported state/action/view/style/accessibility contract from source bytes; declared IR divergence and unmodeled semantics block with registered typed gaps.
- Real local target checks pass for React TypeScript, Vue 2 and Vue 3 template compilers, WeChat DevTools, and Flutter dependency resolution/analyze/widget tests. Flutter records offline-cache and online cold-cache resolution separately.
- Desktop Chrome passed 5/5 current-revision FRT journeys and Pixel 7 Chrome emulation passed 2/2 applicable journeys (3 desktop-only checks intentionally skipped). The real durable Engine lifecycle runs once on desktop Chrome.
- Web Console production dependency audit reports zero known vulnerabilities, and the Next.js 16.3.0 production build passes.
- Separate development, negative, local holdout and synthetic representative corpora remain distinct and are not relabeled as external evidence.
- External campaigns now have executable signed authorization, external-Runner dispatch, privacy/DLP, exact evidence-role and metric validation, independent executor/verifier/approver Ed25519 signatures, and a gate binder. Unsigned, self-verified, stale, incomplete or tampered records fail closed.
- A deterministic qualification generator emits 15 exact cases covering Firefox/WebKit profiles, ArkUI/hvigor and every independent, human, customer, performance, security, DR and production boundary. Its strict preflight executes only local capability probes, binds the source/profile digests and rejects state or authority tampering. After installing and launching exact Firefox 151.0 and WebKit 26.5, 3 cases are `READY_FOR_AUTHORIZED_EXECUTION` and 12 remain `BLOCKED_PRECONDITION`; all 15 external states remain `NOT_RUN`.
- All 15 case adapter IDs now dispatch through an explicit allowlist with no fallback. Their local code contracts execute and pass, producing a report SHA-bound to the exact plan and preflight; the current environment reports 3 `READY_FOR_LOCAL_EXECUTION`, 1 `BLOCKED_TOOLCHAIN` and 11 `REQUIRES_EXTERNAL_AUTHORITY`, with 15/15 external states still `NOT_RUN`.
- Every external check now has a closed, check-specific typed parameter contract. Unknown fields, repository-selected commands, scope widening, stale case/adapter bindings, secret values and weakened safety/independence minimums fail before an authorization can be prepared.
- 28 local protocol tests exercise typed parameter rejection, accepted and adversarial signed records for all nine consolidated external checks, every explicit qualification adapter, recomputed observation tamper detection, privacy-minimized iOS physical-device recording, and the repository gate. These fixtures validate code paths only and are never copied into external evidence.
- The visual gate is configured to reject an absent approved baseline without writing one, and the candidate/approved roots are physically separate. No current-revision visual comparison is claimed.
- All five declared local browser profiles now pass their applicable P0, Axe, keyboard, i18n, network, overflow and local navigation-budget journeys. Exact Firefox 151.0 and WebKit 26.5 runtimes launched successfully; the visual negative gate rejected all five missing approved baselines without creating or promoting one.
- A privacy-minimized physical-device inventory probe detects real devices while discarding device names, UDIDs, serials and raw command output. The current candidate found one physical iOS device but is not external acceptance evidence. The v2 iOS install/launch recorder now requires a physical `devicectl` identity, signed app, exact bundle and running process while persisting only an HMAC pseudonym and minimized metadata; the legacy record was redacted and is not a current-revision rerun.

## Remaining environment and external gaps

- ArkUI native compilation remains `NOT_RUN` on this host because DevEco Studio/hvigor is unavailable. The toolchain runner now executes a real hvigor build when `ELMOS_HVIGORW` or a PATH executable is supplied.
- Independent visual-baseline approval and manual assistive-technology sessions remain `NOT_RUN`.
- A physical iOS programmatic install/launch artifact exists as local engineering evidence; physical-device manual acceptance and the broader authorized device matrix remain `NOT_RUN`.
- Representative real customer source/target repositories and a physically independent holdout corpus remain `NOT_RUN`; generated Counter fixtures are not customer evidence.

## Required external gates

- Execute representative real source and target repositories for every claimed exact route/profile tuple, including a qualified ArkUI environment.
- Run the authorized physical device matrix, independent visual review and assistive-technology sessions.
- Supply physically separate independent holdout and representative customer journey corpora.
- Execute qualified Lean/SMT/model-checking kernels and replay counterexamples for G19 claims.
- Execute authorized performance/capacity, Chaos/HA/DR, penetration/privacy/supply-chain and production SRE gates.
- Obtain accountable customer acceptance, independent review and the named Batch/Production authorities.

The repository-side code required to prepare, dispatch, collect, verify and bind
these campaigns is implemented, including exact parameter validation and all 15
local adapter code paths. Their states remain `NOT_RUN` until the named
external environments and people execute and sign the exact records; a local
agent or JSON edit cannot perform those decisions.

Until these gates run, the maximum result is `READY_FOR_EXTERNAL_GATE`;
`production_operation_authorized=false` and production remains `NOT_CERTIFIED`.
