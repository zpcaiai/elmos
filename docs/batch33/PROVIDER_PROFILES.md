
# Target provider profiles

A target profile must specify exact provider and region tuple, account hierarchy, state backend, identity model, network and DNS design, container and orchestrator strategy, managed services, serverless, gateway, observability, security policies, cost budgets, provision, validate, and destroy commands.

Use provider-neutral contracts for intent and provider-specific profiles for implementation. Do not erase provider-specific limitations: availability-zone semantics, IAM evaluation, networking, consistency, backup, encryption, quota, failover, and billing can differ materially.
