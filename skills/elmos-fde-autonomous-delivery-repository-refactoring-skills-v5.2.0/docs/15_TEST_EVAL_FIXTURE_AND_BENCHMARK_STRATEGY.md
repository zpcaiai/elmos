# 15 — Tests, Evals, Fixtures and Benchmarks

## Test layers

Contract/schema; domain/unit; persistence/RLS; API/event; workflow/resume/cancel; Adapter conformance; authority/tenant/security; native compiler/database/tool; UI/accessibility; end-to-end Golden Route; scale/soak/chaos/recovery.

## Codex Skill evals

Each workflow Skill needs explicit, contextual, adjacent-intent and negative-trigger cases. Grading checks whether Codex selected the right Skill, read the minimum required context, respected ownership, changed only approved scope, ran tests and reported honest blockers.

## Repository fixtures

Include small deterministic fixtures for rapid CI, medium polyglot fixtures for integration, and external open-source/customer-authorized holdouts for route certification. Do not train on customer holdout results or leak them into producer prompts.

## Scale targets

Measure inventory completeness, parse/build success, graph coverage, finding precision/recall on seeded defects, task completion, regression escapes, P50/P95 wall-clock, cost, cache hit, recovery and reviewer load at 10k, 100k, 500k and 1M+ LOC.
