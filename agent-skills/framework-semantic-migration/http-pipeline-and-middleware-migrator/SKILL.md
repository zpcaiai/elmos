---
name: http-pipeline-and-middleware-migrator
description: "Migrate ordered HTTP middleware, filters, interceptors, guards, pipes, endpoint filters, and error boundaries. Use when framework request or response pipeline behavior must be preserved."
---
# HTTP Pipeline and Middleware Migrator
Read `../references/afsm-v1.md`. Build the actual source partial-order graph from registration order, explicit order, conditions, defaults and before/after constraints, then lower it to the target framework.

Preserve short-circuit, async, context, response transformation and error paths. Keep authentication before authorization and the error boundary in its effective position. Generate a composite component only when target primitives cannot express the order, and preserve its internal trace.

