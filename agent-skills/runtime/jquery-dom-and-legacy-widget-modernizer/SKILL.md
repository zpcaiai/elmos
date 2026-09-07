---
name: jquery-dom-and-legacy-widget-modernizer
description: Modernize legacy jQuery versions, plugins, DOM ownership, global events, Ajax, Deferred, widgets, HTML injection, and mixed-framework pages. Use for staged jQuery upgrade or replacement.
---

# jQuery and DOM Modernization

## Workflow

1. Inventory versions, selectors, mutations, events, delegation, Ajax, Deferred, animations, data, plugins, widgets, globals, inline scripts, templates, HTML strings, JSONP, and browser detection.
2. Build a plugin matrix with maintenance, compatibility, security, replacement, source, license, DOM/CSS contract, and consumers.
3. Assign every DOM region `LEGACY_OWNED`, `MODERN_OWNED`, `BRIDGE_OWNED`, or `READ_ONLY`; isolate mixed ownership before migration.
4. Upgrade old 1.x/2.x projects through the relevant Migrate generations, capture every warning, then remove Migrate.
5. Compare Ajax URL, method, serialization, content type, errors, timeout, abort, CSRF, retry, and global handlers.

## Gates

Block unsafe HTML/eval/JSONP, conflicting framework DOM ownership, unsupported plugins, unhandled Deferred semantics, and permanent Migrate dependencies.

## Output

Emit inventory, plugin/ownership matrices, staged upgrade steps, component-island boundaries, contract comparisons, risks, and Evidence.
