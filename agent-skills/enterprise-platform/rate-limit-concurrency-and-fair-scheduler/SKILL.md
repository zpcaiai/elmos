---
name: rate-limit-concurrency-and-fair-scheduler
description: Enforce user, token, tenant, API, IP, Runner, model, and project rate limits plus weighted fair queues, aging, reservations, and safe preemption. Use for multi-tenant fairness and concurrency design.
---

# Rate Limit Concurrency and Fair Scheduler

Read `../references/batch-12-enterprise-platform.md`. Separate security, interactive, standard, batch and background queues; account retries correctly, age low priority and preempt only checkpointable work. Return explicit explainable decisions and queue SLO evidence.

Large tenants cannot starve small tenants and ordinary work cannot starve permanently. Violations block T-D.
