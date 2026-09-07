---
name: multi-scm-compatibility-contract-tests-and-release-gates
description: "Implement unified SCM TCK, provider fixtures, real-provider smoke tests, permission and token tests, webhook signature tests, pagination/rate-limit/revocation/failure injection, compatibility evidence, and mandatory release gates for GitLab, Azure DevOps, Bitbucket Cloud/Data Center, and Gitee."
---

# Objective

Prove each connector implements the same semantics while preserving provider
differences.

# Verification levels

```text
UNIT_VERIFIED
CONTRACT_VERIFIED
FIXTURE_VERIFIED
SANDBOX_INSTANCE_VERIFIED
REAL_CLOUD_VERIFIED
REAL_SELF_MANAGED_VERIFIED
CUSTOMER_INSTANCE_VERIFIED
UNVERIFIED
