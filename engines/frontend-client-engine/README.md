# ELMOS Frontend and Client Engine

This independently runnable TypeScript/Node worker is ELMOS's fourth execution engine. Its repository-verifiable core performs bounded workspace/package discovery, UI route/component/state graph construction, target planning, framework risk classification, visual-environment comparison, accessibility adjudication, client compatibility, and release-gate evaluation without installing dependencies or executing customer code.

The engine also exposes a typed UI project generator for nine exact core profiles: Vue 2, Vue 3, React, React Native with Expo, jQuery, Flutter, HarmonyOS ArkUI, Angular, and Svelte. It generates all 72 directed source-to-target route plans, a target application shell, exact dependency/config manifests, routes, UI IR, target profile, ownership metadata, CI, and fail-closed verification scripts. Static generation is not runtime or certification evidence.

```bash
pnpm install --frozen-lockfile
pnpm check
node dist/src/server.js
curl http://127.0.0.1:8088/engine/v1/capabilities
curl http://127.0.0.1:8088/engine/v1/ui-projects/capabilities
```

Generate a create-only target project:

```bash
pnpm build
pnpm project:generate examples/ui-project-request.json /tmp/customer-console-react
```

The materializer never invokes package managers, SDKs, lifecycle scripts, or customer code on the host. The generated `scripts/verify.sh` requires the exact target Runner and fails closed while the lock, build, browser/device, accessibility, visual, holdout, or certification evidence is absent.

The worker exposes the shared `/engine/v1` capability, scan, plan, generate-project, execute-step, validate, job lookup, and cancellation routes. Static scan and project generation can return content-addressed Evidence while keeping `customerCodeExecuted=false`. Codemods, package installs, builds, browsers, desktop clients, emulators/simulators, real devices, signing, stores, and release providers require separately approved Runners. Until configured, execution returns terminal `FAILED` with empty evidence.

The 22 required Batch 14 accident scenarios are executable in `test/batch14.test.ts`. Six JSON Schema fixtures and the shared OpenAPI contract are also checked. These tests do not claim that a customer UI rendered, that an accessibility manual review occurred, or that any client was published.
