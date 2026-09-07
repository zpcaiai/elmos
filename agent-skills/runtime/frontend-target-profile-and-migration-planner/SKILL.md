---
name: frontend-target-profile-and-migration-planner
description: Select an approved framework-neutral frontend target profile and generate a dependency-safe migration DAG covering Web, desktop, mobile, BFF, design system, browser, accessibility, release, and compatibility constraints.
---

# Frontend Target and Plan

## Workflow

1. Require discovery, UI graph, baseline evidence, compatibility Snapshot, team/platform standards, browser/device ranges, API/BFF contracts, design system, and accessibility target.
2. Keep behavior-preserving modernization, design-system adoption, UX redesign, and client replatforming as separate modes.
3. Choose among in-place upgrade, compatibility build, microfrontend strangler, route/component migration, Web Component bridge, embedded app, rewrite, or keep-and-harden.
4. Order build/runtime, utilities, tokens, components, state/API, leaf routes, core routes, shell, validation, canary, and compatibility removal.
5. Give every compatibility layer an owner, expiry, usage metric, removal step, rollback, and acceptance gate.

## Gates

Require named product approval for navigation, workflow, field, role, mobile interaction, desktop capability, accessibility exception, brand, UX redesign, replatform, or full rewrite changes. Do not default all clients to React or any single framework.

## Output

Emit the target profile, rejected alternatives, deterministic DAG, per-route steps, Runner requirements, risk register, approvals, and Evidence references.
