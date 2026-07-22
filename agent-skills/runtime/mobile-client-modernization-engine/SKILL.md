---
name: mobile-client-modernization-engine
description: Modernize Android, iOS, React Native, Flutter, Cordova, and Ionic clients across navigation, permissions, offline sync, push, deep links, WebView, secure storage, devices, and store release.
---

# Mobile Client Modernization

## Workflow

1. Inventory platform/OS bounds, screens, navigation, state, network/auth, secure storage, offline database, background work, push, links, device permissions, WebViews, analytics, crash, and store release.
2. Choose native incremental, Views-to-Compose, UIKit-to-SwiftUI, hybrid upgrade, cross-platform replatform, WebView reduction, or retained native device layer from evidence—not code-reuse preference.
3. Preserve old, current, and next client versions through a time-bounded API/BFF compatibility matrix.
4. Validate offline conflict, retry, duplicate, ordering, deletion, clocks, transitions, background, and battery; require operation idempotency.
5. Compare permission timing/denial/revocation, push payload/lifecycle, deep-link routing/auth/input, and simulator versus real-device results.

## Gates

Never use client version as authorization. Do not sign production packages, submit stores, force upgrade, accept privacy text, or treat simulator evidence as real-device evidence without approval.

## Output

Emit capabilities, version contracts, offline/deep-link/push results, release candidate metadata, cohort plan, blockers, and Evidence.
