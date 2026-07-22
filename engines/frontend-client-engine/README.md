# ELMOS Frontend and Client Engine

This independently runnable TypeScript/Node worker is ELMOS's fourth execution engine. Its repository-verifiable core performs bounded workspace/package discovery, UI route/component/state graph construction, target planning, framework risk classification, visual-environment comparison, accessibility adjudication, client compatibility, and release-gate evaluation without installing dependencies or executing customer code.

```bash
pnpm install --frozen-lockfile
pnpm check
node dist/src/server.js
curl http://127.0.0.1:8088/engine/v1/capabilities
```

The worker exposes the shared `/engine/v1` capability, scan, plan, execute-step, validate, job lookup, and cancellation routes. Static scan can return content-addressed Evidence while keeping `customerCodeExecuted=false`. Codemods, package installs, builds, browsers, desktop clients, emulators/simulators, real devices, signing, stores, and release providers require separately approved Runners. Until configured, execution returns terminal `FAILED` with empty evidence.

The 22 required Batch 14 accident scenarios are executable in `test/batch14.test.ts`. Six JSON Schema fixtures and the shared OpenAPI contract are also checked. These tests do not claim that a customer UI rendered, that an accessibility manual review occurred, or that any client was published.
