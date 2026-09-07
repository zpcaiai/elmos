---
name: flask-wsgi-asgi-modernization-engine
description: Inventory and modernize Flask, Werkzeug/Jinja dependencies, blueprints, extensions, contexts, sessions, routes, app factories, WSGI servers, async views, and explicit ASGI strategies. Use for Flask upgrades, context regressions, extension compatibility, or WSGI/ASGI architecture decisions.
---

# Flask, WSGI, and ASGI Modernization Engine

## Separate upgrade from redesign

Inventory Flask and Pallets versions, blueprints/routes, extensions, app factory, request/application contexts, session, error handlers, CLI, templates/static assets, middleware, WSGI server, workers, and async views. Resolve live versions through the compatibility snapshot.

Move global app creation toward `create_app()` only when imports, extension initialization, CLI, blueprints, tests, and context lifetime remain correct. Detect background/thread access to `current_app`, `g`, `request`, or `session` outside valid context.

Evaluate every extension for Python/Flask compatibility, maintenance, replacement, initialization, and migration steps. Generate feature-version edges for removed context stacks, config proxies, JSON providers, session behavior, hooks, and version access.

Keep Flask WSGI by default. Select an adapter, Quart/FastAPI/other rewrite, or service split only for evidenced WebSocket, long-lived connection, concurrency, or ASGI middleware needs. Never rewrite frameworks merely to appear modern.

Accept only after route/method/converter/query/form/JSON/cookie/session/error/redirect/header/streaming contracts and worker/timeout/thread/process/signal/shutdown behavior are compared.

