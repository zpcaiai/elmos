---
name: django-modernization-engine
description: Inventory and incrementally modernize Django versions, settings, URLs, middleware, ORM, migrations, authentication, sessions, admin, third-party apps, and WSGI/ASGI deployment. Use for Django legacy assessment, upgrade DAGs, deprecation cleanup, or behavior validation.
---

# Django Modernization Engine

## Inventory the whole application

Record Django/Python versions, settings modules, installed apps, middleware, URLs, models/migrations, views/templates/forms/admin, auth/session/cache/storage, signals, commands, Celery/Channels/DRF, third-party apps, and deployment servers.

Resolve every target patch through the dated compatibility snapshot. For multi-feature upgrades, move from the latest patch of the current feature series through each intermediate feature series. Enable warnings, fix controlled Django deprecations, and rerun tests at every edge. Do not jump directly from an old series to the newest series.

Treat third-party app Python/Django compatibility as a hard constraint. Record maintenance, target version, replacement, and migration guide. Block or require an approved replacement when a critical app has no compatible release.

## Preserve behavior

Compare URL/reverse behavior, middleware order and exception/streaming/async behavior, QuerySet/aggregation/order/null/timezone/raw SQL/transactions, fresh and upgrade migrations, schema/data invariants, login/password/session/permissions/CSRF/cookies/redirects, and static/storage behavior. Never copy secrets into new settings.

Keep WSGI unless evidence justifies ASGI. Accept only after system checks, migrations, unit/integration, HTTP/HTML, auth/session, database, performance, and static checks pass for every feature edge.

