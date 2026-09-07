---
name: github-app-registration-key-installation-and-permission-6bc545c1
description: "Implement GitHub App configuration, private-key references and rotation, JWT creation, app validation, installation tenant binding, permission snapshots, suspension, deletion, access expansion review, and tombstones."
---

# Objective

Manage GitHub App and Installation lifecycle as durable enterprise assets.

# Domain model

Create:

```text
scm.github_apps
scm.github_app_versions
scm.github_app_key_references
scm.github_app_key_rotations
scm.github_app_permission_profiles
scm.github_installations
scm.github_installation_versions
scm.github_installation_permissions
scm.github_installation_accounts
scm.github_installation_events
scm.github_installation_tombstones
scm.github_installation_binding_decisions
