---
name: frontend-backend-coordinated-release-and-cutover
description: Govern coordinated Web, desktop, Android, iOS, BFF, gateway, backend, authentication, design-system, CDN, service-worker release, rollback, compatibility, and decommission stages.
---

# Coordinated Client Cutover

## Workflow

1. Freeze a version matrix for every active client/BFF/backend combination and define minimum, recommended, expiry, notice, and forced-upgrade policy.
2. Advance exactly through internal, canary, progressive, full, stability, read-only, and decommission gates; never skip stages.
3. Use route/tenant/user/region/flag/host/cookie/header cohorts for Web, rings/channels for desktop, and approved phased store/remote-config cohorts for mobile.
4. Validate cookies, session, CSRF, refresh/logout, CDN/HTML/chunks, old tabs, service-worker activation/cache/data migration, and rollback behavior.
5. Observe errors, auth, visual, accessibility, performance, journeys, tickets, conversion, abandonment, version usage, and compatibility-expiry evidence.

## Gates

Require named human approval for Full, forced upgrade, signing/store submission, and decommission. Never assume mobile rollback can downgrade devices. Keep backend compatibility until actual active usage satisfies policy.

## Output

Emit version matrix, compatibility window, release/cohort plans, promotion decisions, platform-specific rollback, stability observations, decommission checks, and Evidence.
