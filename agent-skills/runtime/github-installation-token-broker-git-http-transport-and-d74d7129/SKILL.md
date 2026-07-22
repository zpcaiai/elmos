---
name: github-installation-token-broker-git-http-transport-and-d74d7129
description: "Implement purpose-bound GitHub installation-token issuance, permission/repository scope intersection, in-memory token caching, Git HTTP credential handling, clone/fetch/push contracts, explicit revocation, and unknown-result reconciliation."
---

# Objective

Provide short-lived GitHub authority only to an approved workload and task.

Target flow:

Runner task requests Git purpose
→ control plane validates tenant, installation, repository, permission, task
→ app JWT issued
→ installation token scoped
→ token lease delivered to Runner
→ Git operation through temporary credential helper
→ credential removed
→ token revoked or expires
→ operation receipt and audit

# Token purposes

```text
PROVIDER_DISCOVERY
INSTALLATION_REPOSITORY_SYNC
REPOSITORY_METADATA_READ
SOURCE_CLONE
SOURCE_FETCH
DELIVERY_BRANCH_PUSH
PULL_REQUEST_CREATE
CHECKS_PUBLISH
COMMIT_STATUS_PUBLISH
