---
name: angularjs-and-legacy-angular-modernizer
description: Modernize AngularJS and legacy Angular modules, scopes, directives, services, routes, RxJS, Material, builders, tests, and hybrid boundaries. Use for staged Angular migration after baseline and target approval.
---

# Angular Modernization

## Workflow

1. Inventory AngularJS modules, controllers, directives, scopes, watchers, digest events, transclusion, services, routes, forms, `$http`, `$q`, plugins, and templates separately from modern Angular constructs.
2. Choose hold-and-harden, `ngUpgrade`, microfrontend/route strangler, or approved rewrite; document every hybrid boundary and exit date.
3. Build state dependency and behavior tests before lowering `$watch`, `$broadcast`, `$emit`, or digest-driven side effects.
4. Upgrade modern Angular one major at a time with the compatible official migration, build, tests, and rollback evidence at each step.
5. Treat NgModule-to-standalone, Signals, control flow, SSR/hydration, RxJS, Zone, and Material as independent changes.

## Gates

Block mechanical watcher conversion, skipped majors, unresolved plugins, behavioral RxJS changes, unapproved Material visual changes, and compatibility layers without expiry.

## Output

Emit Angular inventory, hybrid map, per-major plan, codemod candidates, behavioral/visual risks, validation obligations, and Evidence.
