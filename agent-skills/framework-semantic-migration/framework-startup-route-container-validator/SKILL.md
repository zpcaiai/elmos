---
name: framework-startup-route-container-validator
description: "Validate static framework models, isolated bootstrap, DI/container resolution, route/OpenAPI/job/consumer discovery, smoke requests, and shutdown. Use before Batch 7 F-B through F-D gates."
---
# Framework Startup Route and Container Validator
Read `../references/afsm-v1.md`. Run in an approved isolated environment with test/fake database, broker, cache, secrets and external services; deny production access and disable real scheduler and consumer execution during discovery.

Record static model, bootstrap, container resolution, route/OpenAPI discovery, smoke and shutdown separately with backend/environment/artifact references. Do not suppress startup failures or equate startup, health green or discovery with behavior equivalence.

