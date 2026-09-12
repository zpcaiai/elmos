# git-provider-adapter

**Providers:** GitHub/GitLab/Gitea/Azure Repos

**Scope:** repository source, pull requests, reviews, webhooks.

This directory is an implementation contract, not a live integration. Implement the abstract Elmos port, negotiate capabilities and versions, enforce environment-owned authority, return typed results, and pass every case in `conformance.yaml`. The Adapter never owns semantic truth, routing, or completion.
