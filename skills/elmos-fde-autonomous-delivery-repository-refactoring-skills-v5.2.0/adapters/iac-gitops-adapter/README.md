# iac-gitops-adapter

**Providers:** Terraform/Pulumi/Helm/ArgoCD/Flux

**Scope:** infrastructure semantics, drift, plans and controlled rollout.

This directory is an implementation contract, not a live integration. Implement the abstract Elmos port, negotiate capabilities and versions, enforce environment-owned authority, return typed results, and pass every case in `conformance.yaml`. The Adapter never owns semantic truth, routing, or completion.
