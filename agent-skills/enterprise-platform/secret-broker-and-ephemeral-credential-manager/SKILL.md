---
name: secret-broker-and-ephemeral-credential-manager
description: Issue least-privilege, job- and Runner-bound ephemeral credentials through workload identity exchange or local brokers. Use for Git, package, database, cloud, model, Artifact, signing, or KMS access.
---

# Secret Broker and Ephemeral Credential Manager

Read `../references/batch-12-enterprise-platform.md`. Deliver secrets in memory or short-lived mounts, default to non-renewable leases, audit reference access and revoke at job end. Offline secrets remain under the customer-local authority.

Never put values in job JSON, source, shared config or logs. Cross-tenant retrieval or broker fail-open blocks T-C.
