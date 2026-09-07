---
name: artifact-secure-transfer-and-relay
description: Govern tenant-isolated encrypted, signed, resumable Artifact transfer among Control Plane, Runner, customer relay, store, and offline media. Use for job, snapshot, UIR, Patch, evidence, image, or bundle movement.
---

# Artifact Secure Transfer and Relay

Read `../references/batch-12-enterprise-platform.md`. Decide whether content may leave the customer environment, bind sender/receiver, tenant key, digest, signature and expiry, and verify after transfer. Use short one-time download grants and record metadata-only/redaction choices.

Digest/signature failure, cross-tenant path or unapproved source upload blocks T-C/T-E.
