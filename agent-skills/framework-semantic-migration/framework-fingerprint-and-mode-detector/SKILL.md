---
name: framework-fingerprint-and-mode-detector
description: "Detect Spring Boot, FastAPI, ASP.NET Core, NestJS, or Express framework versions and runtime modes from repository evidence. Use at the start of Batch 7 framework migration or whenever the active framework model is uncertain."
---
# Framework Fingerprint and Mode Detector
Read `../references/afsm-v1.md`. Inspect resolved dependencies, entry points, annotations/decorators/attributes, builder registrations and configuration together. Require at least two independent evidence kinds and an exact or explicitly unresolved version.

Distinguish Spring MVC from WebFlux, ASP.NET Controllers from Minimal APIs, NestJS Express from Fastify, and Express third-party composition. Emit the fingerprint, components, evidence references, confidence and diagnostics. Block ambiguous, mixed or single-signal conclusions.

