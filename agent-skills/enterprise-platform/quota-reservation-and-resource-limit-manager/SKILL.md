---
name: quota-reservation-and-resource-limit-manager
description: Atomically enforce inherited hard/soft quotas, reservations, bursts, resets, and admission behavior across runs, tokens, compute, storage, users, Runners, and data volume. Use for capacity and Noisy Neighbor control.
---

# Quota Reservation and Resource Limit Manager

Read `../references/batch-12-enterprise-platform.md`. Resolve tenant-to-project limits, reserve before dispatch/model use, commit or release idempotently after crashes, and return admit/queue/throttle/reject/approval/overage decisions. Offline installations enforce signed local quota.

Project admins cannot override hard tenant limits. Any bypass or leaked reservation blocks T-D.
