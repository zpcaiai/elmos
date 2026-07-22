---
name: tenant-encryption-and-key-isolation-manager
description: Govern tenant-specific encryption keys for databases, Artifacts, audit, backups, and model context. Use for key hierarchy, rotation, revocation, recovery, or crypto-shredding plans.
---

# Tenant Encryption and Key Isolation Manager

Read `../references/batch-12-enterprise-platform.md`. Record platform/tenant/data-key hierarchy, key mode, versions, rotation state, backup recovery and KMS failure behavior without storing key material. Use new keys for new data and support controlled background re-encryption.

Shared tenant data keys, logged key values, untested backup keys or crypto-shredding under Legal Hold block T-E.
