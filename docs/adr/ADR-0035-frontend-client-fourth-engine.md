# ADR-0035: Frontend and client modernization as a fourth execution engine

## Status

Accepted for Batch 14 on 2026-07-21.

## Context

Framework compilation alone cannot establish client migration success. Routes, forms, state, permissions, sessions, local/offline data, BFF contracts, visual rendering, accessibility, native desktop/device integration, mobile-version coexistence, distribution channels, and user journeys cross framework and backend boundaries. Web, desktop, Android, and iOS also require different host capabilities and rollback semantics.

## Decision

Add an independently runnable TypeScript/Node `ELMOS_FRONTEND_CLIENT` engine. It is the fourth source/client execution engine beside Java, .NET, and Python and reuses the existing Tenant, Workflow, Runner, Evidence, Risk, Approval, Delivery, Portfolio, Audit, Billing, and Composite authorities.

Keep repository-safe discovery, graph construction, planning, and policy evaluation deterministic and non-executing. Route package installation, builds, browser rendering, desktop processes, emulators/simulators, real devices, visual capture, dynamic accessibility checks, signing, stores, and provider mutations to approved capability-specific Runners. The Java control plane evaluates release authority but cannot run customer code.

Treat behavior-preserving modernization, design-system adoption, UX redesign, and replatforming separately. Require approval for product-flow, role, field, brand, accessibility-exception, device-capability, forced-upgrade, full-release, and decommission decisions. An automated accessibility scan or unstable screenshot environment cannot become a pass.

## Consequences

- AngularJS/Angular, Vue, React, and jQuery migrations use staged, removable compatibility paths rather than one-shot version replacement.
- Desktop and mobile remain capability-specific; simulator results do not replace real-device evidence, and mobile rollback never assumes devices can be downgraded.
- BFFs may adapt and aggregate but do not own core business rules or user authorization.
- Visual baselines bind the complete rendering environment and require human approval; approved redesign uses a separate target baseline.
- V14 stores 71 tenant-scoped projections with forced RLS and append-only evidence/decision history. F001–F017 define reusable operator contracts, and 22 executable accident scenarios form the minimum repository acceptance suite.

## External gates

Approved image/host digests, browsers, fonts, desktop hosts, Android/iOS devices, customer applications, test identities, privacy-safe fixtures, manual screen-reader reviews, signing keys, store accounts, CDN/BFF/backend providers, telemetry, and rollback/decommission drills remain external Evidence gates.
