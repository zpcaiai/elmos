---
name: rest-endpoint-route-migrator
description: "Migrate REST routes, methods, matching constraints, status codes, versions, content types, streaming, multipart, SSE, and WebSocket boundaries. Use for AFSM endpoint lowering."
---
# REST Endpoint and Route Migrator
Read `../references/afsm-v1.md`. Preserve path, method, host/header/query/media constraints, route names, versioning, precedence, case/trailing-slash behavior and response status.

Model unsupported constraints as validators, middleware or handler guards; never delete them. Detect duplicate or shadowed routes. Keep streaming and multipart resource limits explicit and block materialization or route conflicts.

