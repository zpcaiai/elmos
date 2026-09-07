---
name: github-enterprise-network-proxy-custom-ca-rate-limit-ma-a2cc0a68
description: "Implement GHES connectivity profiles, outbound proxies, custom CA trust, redirect and DNS security, maintenance detection, rate-limit budgeting, backoff, circuit breakers, provider health, HA hostname handling, and resilient webhook/API behavior."
---

# Objective

Support private GHES instances without weakening TLS or causing uncontrolled
API traffic.

# Domain model

Create:

```text
scm.github_network_profiles
scm.github_proxy_profiles
scm.github_ca_trust_profiles
scm.github_provider_health_checks
scm.github_rate_limit_snapshots
scm.github_rate_limit_budgets
scm.github_rate_limit_events
scm.github_provider_circuit_breakers
scm.github_provider_maintenance_events
scm.github_connectivity_incidents
