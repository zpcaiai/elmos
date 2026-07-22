---
name: vue2-to-vue3-modernizer
description: Modernize Vue 2 applications through Vue 2.7, Vue compatibility build, Vue 3, Router, state, SFC, render functions, plugins, UI libraries, and build tools. Use for staged Vue modernization.
---

# Vue Modernization

## Workflow

1. Inventory Vue version, global APIs, Options/Composition APIs, SFCs, render/functional components, filters, directives, mixins, plugins, Vuex/Pinia, Router, event bus, slots, transitions, UI library, SSR, CLI, and bundler.
2. Use Vue 2.7 as an optional intermediate point, then fix warnings and build tooling before enabling `@vue/compat`.
3. Record compatibility warnings per component and migrate Router, store, UI library, templates, render functions, directives, slots, and transitions separately.
4. Switch components to Vue 3 mode incrementally; remove `@vue/compat` or obtain an explicit time-bounded exception.

## Gates

Mark private VNode/runtime APIs, unsupported UI libraries, undocumented render behavior, or unresolved event/store semantics as partial or ineligible. Do not assume compatibility mode makes them safe.

## Output

Emit inventory, compatibility eligibility, per-component warning ledger, staged steps, visual/behavior obligations, removal gate, and Evidence.
