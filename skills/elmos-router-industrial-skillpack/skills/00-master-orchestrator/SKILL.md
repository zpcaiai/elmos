# Skill 00 — Master Orchestrator

## Goal
Coordinate all routing-plane work as a controlled migration, not a big-bang rewrite.

## Tasks
1. Inventory existing model/provider calls, including hidden direct HTTP calls.
2. Identify task/step identifiers, durable events, billing, auth, permission context, and trace context.
3. Produce a dependency map:
   `caller -> routing -> adapter -> provider -> result commit`.
4. Create feature flags:
   - `router_v2_enabled`
   - `shadow_route_enabled`
   - `native_lane_enabled`
   - `openrouter_fallback_enabled`
5. Define coexistence:
   legacy path remains callable until certification gates pass.
6. Freeze package/module boundaries before implementation.

## Acceptance
- All known model calls are inventoried.
- No new provider call bypasses the new SPI.
- Rollback to legacy route requires configuration only.
