---
name: multi-tenant-scheduling-isolation
description: Enforce tenant isolation, per-account three-task concurrency, fair scheduling, quotas, cache separation, leases and backpressure for parallel ETGB execution.
---

# Multi-Tenant Scheduling and Isolation

## Invariants

- each account has at most three active Elmos tasks unless a separately approved plan changes the quota;
- tenant/project/task ownership follows every run, shard, case, workspace, cache entry, checkpoint, artifact, trace and usage event;
- no tenant can starve another through unlimited shards or retries;
- priority cannot bypass P0 safety, budget or authority gates;
- leases and fencing prevent duplicate active owners.

## Scheduling

Use stable sharding by case/corpus/candidate/seed digest. Apply weighted fair queuing across tenants, then account concurrency and project priority. Reserve capacity for short control-plane operations so cancellations, heartbeats and compensation are not starved by long builds.

## Quotas and backpressure

Enforce active tasks, active shards, CPU/memory/storage, provider requests, tokens, credits and artifact retention. On pressure, stop admitting optional work, reduce shard concurrency or checkpoint-and-pause. Never silently drop accepted cases.

## Isolation

Use PostgreSQL RLS or equivalent plus object-store prefixes and KMS/access policies. Cache keys include tenant unless an artifact is explicitly public and content-addressed. Shared dependency caches are read-only to untrusted builds and cannot hold credentials.

## Lease behavior

A shard owner heartbeats a bounded lease. Takeover occurs only after expiry and increments fencing. Stale workers cannot mutate workspaces, publish evidence, post usage or perform external effects.

## Required tests

- fourth concurrent task rejected/queued;
- tenant fairness and priority inversion;
- cross-tenant cache/artifact/trace/database access;
- duplicate shard lease and stale fence;
- cancellation under queue pressure;
- quota exhaustion and recovery;
- million-LOC workload coexisting with short tasks.

## Implementation

Use the PostgreSQL RLS/schema, stable shards in `etgb/planner.py`, Environment authority and account-aware control-plane scheduling.
