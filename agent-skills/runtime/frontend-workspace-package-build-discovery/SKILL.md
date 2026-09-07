---
name: frontend-workspace-package-build-discovery
description: Discover frontend workspaces, package managers, lockfiles, build tools, entry points, environments, browser targets, tests, desktop shells, and mobile projects. Use before planning or running any Batch 14 modernization.
---

# Frontend Workspace Discovery

## Workflow

1. Read only the authorized immutable Snapshot; reject absolute paths, traversal, and escaped symlinks.
2. Inventory `package.json`, npm/Yarn/pnpm/Bower locks, workspaces, Angular/Nx/Turbo/Lerna, Vite/Webpack/Rollup, Gulp/Grunt, TypeScript/Babel, test, Story, Electron, Cordova, Capacitor, Android, iOS, and browser manifests.
3. Infer the effective package manager from CI commands, `packageManager`, Corepack, lockfile, workspace protocol, registry, patches, Git dependencies, and local links.
4. Separate build-time, runtime, public, secret-reference, and client-exposed environment values. Redact values and flag secret-like public variables.
5. Emit independent build targets, entry points, browser/WebView ranges, test systems, release targets, and confidence-backed findings.

## Gates

Block execution on missing workspace, unresolved manager, conflicting locks, unpinned dependencies, unsupported runtime, exposed client secrets, or unresolved browser policy. Do not run install or build commands during discovery.

## Output

Produce workspace inventory, package graph, build targets, entry points, environment inventory, browser profile, test inventory, Evidence references, and unresolved unknowns.
