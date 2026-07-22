---
name: aspnet-framework-to-aspnet-core-migrator
description: Plan and execute evidence-bound ASP.NET Framework modernization using in-place or incremental ASP.NET Core patterns without pretending Web Forms UI is automatically portable.
---

# ASP.NET Framework to ASP.NET Core Migrator

Inventory Web Forms, MVC 5, Web API 2, System.Web usage, modules/handlers, routes/endpoints, auth, session, cache, HttpContext, bundling, configuration, serialization and third-party controls.

## Decision

Use in-place only for bounded applications with adequate tests and compatible features. For large production systems, Web Forms, heavy System.Web or zero-downtime needs, prefer side-by-side ASP.NET Core with YARP route migration. Use System.Web adapters only as an explicit transition with either a removal step or approved long-term ownership decision.

Web Forms pages, ViewState, server controls and third-party UI are `REWRITE_REQUIRED`. Extract portable business libraries and contracts; do not claim automatic page conversion. Authentication, authorization, session, cache, cookie/data-protection, routing and error behavior each receive separate gates.

## Required output

Produce ASP.NET inventory, endpoint/route map, selected migration pattern, route-wave plan, UI rewrite backlog, adapter/YARP configuration attribution, exit decisions and HTTP/auth/session/serialization validation obligations.

Block when route ownership is ambiguous, shared session/auth cannot be verified, unsupported controls have no decision, or the proxy/adapter would become an unowned permanent architecture.
