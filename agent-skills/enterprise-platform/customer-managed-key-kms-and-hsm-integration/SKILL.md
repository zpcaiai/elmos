---
name: customer-managed-key-kms-and-hsm-integration
description: Integrate cloud/customer KMS, external key managers, HSM, PKCS#11, and offline key servers for encrypt/decrypt/wrap/sign/rotate/revoke operations. Use for CMK or customer-held-key architecture and drills.
---

# Customer Managed Key KMS and HSM Integration

Read `../references/batch-12-enterprise-platform.md`. Use workload authentication and least privilege, separate signing from encryption, back up metadata and define fail-closed read/write behavior during outage. Never export customer-held key plaintext.

Untested rotation/revocation, shared keys, cloud-dependent offline keys or unsafe KMS failure blocks T-E/T-F.
