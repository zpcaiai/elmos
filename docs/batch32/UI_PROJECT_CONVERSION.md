# Batch 32 project-level UI conversion

## Outcome

ELMOS has a framework-neutral, typed UI project generator for nine exact core target profiles:

| Target | Exact profile | Project generator | Runtime evidence | Certification |
|---|---|---:|---:|---:|
| Vue 2 | 2.7.16 | ready, legacy conditional | `NOT_RUN` | `NOT_CERTIFIED` |
| Vue 3 | 3.5.40 | ready | `NOT_RUN` | `NOT_CERTIFIED` |
| React | 19.2.8 | ready | `NOT_RUN` | `NOT_CERTIFIED` |
| React Native | 0.86.0 with Expo 57.0.8 | ready | `NOT_RUN` | `NOT_CERTIFIED` |
| jQuery | 4.0.0 | ready, legacy conditional | `NOT_RUN` | `NOT_CERTIFIED` |
| Flutter | 3.44.1 / Dart 3.12.1 | ready | `NOT_RUN` | `NOT_CERTIFIED` |
| HarmonyOS ArkUI | 6.0.0 API 20 | ready | `NOT_RUN` | `NOT_CERTIFIED` |
| Angular | 22.0.8 | ready | `NOT_RUN` | `NOT_CERTIFIED` |
| Svelte | 5.56.8 | ready | `NOT_RUN` | `NOT_CERTIFIED` |

The generator derives 72 directed routes (`9 * 8`). Direction matters. Vue 2 to React and React to Vue 2 are different routes with different source evidence, transformations, risks, and certification.

## What project-level means

Each generated project contains:

- an exact target profile and directional conversion manifest;
- a target-native application entry point and navigation shell;
- every UI IR route represented in the target route/navigation contract;
- package/build/SDK configuration for the selected target;
- a preserved typed UI IR snapshot and open-obligation inventory;
- environment, editor, ignore, ownership, CI, and verification configuration;
- explicit `NOT_RUN` states for dependency lock, build, startup, browser/device journey, accessibility, visual parity, holdout, signing, and certification.

The static generator never claims that source behavior has been executed or that generated components are equivalent. Route, state, effect, form, API, auth, permissions, lifecycle, accessibility, visual, i18n, offline, device, signing, and release obligations must be replayed with real source and target applications.

## Input contract

The request schema is `schemas/batch32/ui-project-generation.schema.json`. It requires:

- exact source framework/version/platform and a different exact target profile;
- stable project, application, package, and bundle identities;
- an immutable source snapshot digest plus routes, views, components, state, actions, effects, forms, bindings, permissions, resources, design tokens, accessibility, native boundaries, and explicit unknowns;
- stable IDs, source traces, resolved references, unique paths, auth flags, and deep-link flags.

The generator rejects floating versions, same-source-and-target requests, path traversal, duplicate IDs or paths, missing route components, and unresolved UI IR references.

## Commands

```bash
cd engines/frontend-client-engine
pnpm install --frozen-lockfile
pnpm check
pnpm project:generate examples/ui-project-request.json /tmp/customer-console-react
```

The materializer does not invoke package managers, SDKs, lifecycle scripts, or
customer code on the host. Dependency lock resolution, target build/startup,
and browser/device journeys remain `NOT_RUN` until an approved Runner executes
them.

The output directory must be absent or empty. Existing customer files are never overwritten.

## Additional mainstream profiles

The next support tier should include:

1. Next.js and Nuxt as separate SSR/SSG/server-component target profiles, not aliases for React and Vue.
2. Jetpack Compose and SwiftUI for native Android and Apple lifecycle, permission, background, signing, and store contracts.
3. Electron and Tauri for desktop process, IPC, updater, native capability, packaging, and code-signing contracts.
4. Ionic/Capacitor, uni-app, and WeChat Mini Program for hybrid and China-specific multi-end contracts.

These appear as `PLANNED` or `DETECTED_ONLY` capabilities. They are intentionally outside the 72 core generated routes until their exact toolchains, project templates, runtime journeys, holdout corpora, and Runner profiles exist.
