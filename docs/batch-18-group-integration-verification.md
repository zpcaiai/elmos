# Batch 18 group integration verification

Verified locally on 2026-07-22. The authoritative scope is Skills 669–745, GITM, M18-A through M18-H, 12 reports, four schemas and the V27 `group_integration` projections.

Repository tests cover exact Skill inventory, source digest, sequential gates, strict contracts, artifact shape, forced RLS and append-only declarations. All 77 Skill Creator packages validate. No clean-team data was accessed; no identity/data merge, Day 1 change, Wave cutover, TSA exit, carve-out, legacy retirement or financial synergy recognition occurred. All 77 field rows remain `NOT_RUN`, and the repository cannot establish `group-integration-completed`.

Current local results and PostgreSQL evidence are recorded in `docs/company-series-verification.md`.
