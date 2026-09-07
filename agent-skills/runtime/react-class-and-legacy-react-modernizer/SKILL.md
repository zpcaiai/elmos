---
name: react-class-and-legacy-react-modernizer
description: Classify and modernize React class components, legacy lifecycle/context/ref/root APIs, HOCs, render props, state, effects, routing, forms, SSR, and tests. Use when behavior-preserving React modernization is requested.
---

# React Legacy Modernization

## Workflow

1. Inventory class/function components, lifecycle, state, Context, refs, HOCs, render props, legacy roots, Strict Mode, stores, router, forms, styling, SSR, and tests.
2. Classify each class as safe function conversion, effect, layout effect, custom hook, retained error boundary, temporary class, or manual redesign.
3. Preserve subscription cleanup, event listeners, timers, abort/race behavior, dependency semantics, ref/static/type behavior, and memoization.
4. Choose state shape deliberately among state, reducer, custom hook, server state, URL state, or approved global store.
5. Run behavior and Strict Mode regression in a fresh approved Runner.

## Gates

Keep `componentDidCatch`/error boundaries as classes or approved abstractions. Escalate `getSnapshotBeforeUpdate`, stale-closure, DOM measurement, derived-state, and direct-DOM risks; never force every class into Hooks.

## Output

Emit classification, patch candidates, preserved invariants, tests, unresolved risks, and Evidence.
