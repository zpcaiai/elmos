---
name: ui-route-component-state-and-behavior-graph
description: Build an evidence-backed cross-framework graph of routes, pages, components, state, events, forms, permissions, APIs, desktop IPC, mobile navigation, and user journeys. Use after frontend workspace discovery.
---

# UI Semantic Graph

## Workflow

1. Analyze Angular/AngularJS routers, Vue Router, React Router, server routes, jQuery history, Electron navigation, mobile navigation, deep links, menus, flags, and remote modules.
2. Keep Route, Page, Component, Component Instance, State, Event, Side Effect, API, Form, and Permission nodes distinct.
3. Track state ownership across component, form, store, server cache, URL, session, cookie, local storage, IndexedDB, desktop store, mobile preferences, and offline database.
4. Record `ROUTES_TO`, `RENDERS`, `READS_STATE`, `WRITES_STATE`, `DISPATCHES`, `CALLS_API`, `REQUIRES_PERMISSION`, `VALIDATES_FORM`, `NAVIGATES`, and persistence edges.
5. Derive candidate journeys from tests, approved analytics, routes, documentation, and customer definitions with provenance.

## Gates

Mark runtime-named components, plugins, CMS entries, feature-flag targets, and remote modules as `DYNAMIC_UI_DEPENDENCY` when unresolved. Never treat hidden UI as backend authorization.

## Output

Emit route, component, state, event, API-call, form-contract, permission, and journey graphs with Snapshot references, confidence, and Evidence.
