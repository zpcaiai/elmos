---
name: github-provider-profile-version-discovery-and-capabilit-98fa3c1a
description: "Implement immutable GitHub Cloud/GHES provider profiles, endpoint normalization, instance-version discovery, REST API version selection, capability probing, compatibility state, and readiness."
---

# Objective

Represent each GitHub service as a versioned, approved provider instance.

Never scatter GitHub base URLs and API-version logic across adapters.

# Domain model

Create:

```text
scm.github_providers
scm.github_provider_versions
scm.github_provider_endpoints
scm.github_provider_capability_snapshots
scm.github_provider_api_versions
scm.github_provider_compatibility_results
scm.github_provider_readiness
scm.github_provider_events
