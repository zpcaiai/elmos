---
name: enterprise-git-proxy-mirror-object-cache-and-offline-fetch
description: "Implement provider-scoped Git proxy and CA profiles, authenticated mirror profiles, tenant-safe object caches, alternates and multi-pack-index governance, cache promotion and verification, offline prefetch bundles, bandwidth reduction, cache eviction, poisoning prevention, and recovery."
---

# Objective

Reduce repeated Git transfer without letting caches bypass current
authorization or leak source across tenants.

# Domain model

Create:

```text
workspace.git_transport_profiles
workspace.git_proxy_profiles
workspace.git_ca_profiles
workspace.git_mirror_profiles
workspace.git_mirrors
workspace.git_mirror_sync_runs
workspace.git_object_cache_profiles
workspace.git_object_caches
workspace.git_cache_namespaces
workspace.git_cache_write_leases
workspace.git_cache_objects
workspace.git_cache_packfiles
workspace.git_cache_verification_runs
workspace.git_cache_promotion_runs
workspace.git_cache_eviction_runs
workspace.git_offline_packages
workspace.git_offline_package_members
workspace.git_offline_import_runs
workspace.git_cache_findings
