---
name: sandbox-network-policy
description: Build or review ELMOS sandbox egress controls, versioned allowlists, DNS/IP validation, proxy enforcement, and fail-closed network evidence. Use for dependency-download windows or workspace networking.
---

# Sandbox Network Policy

Start every workspace with no external network. Open only a time-bounded, versioned dependency-download route through an enforcing proxy when policy explicitly allows it.

## Required workflow

1. Attach the workspace to an internal Docker network by default.
2. Resolve a versioned policy for tenant, repository, operation, ecosystem, and time window.
3. Allow exact HTTPS destinations needed for declared dependency repositories; reject arbitrary wildcards and IP literals.
4. Re-resolve DNS and reject loopback, link-local, multicast, private, metadata-service, and otherwise forbidden addresses.
5. Route traffic through an auditable proxy and prevent direct egress bypass.
6. Close the window after the dependency operation and store bounded decision/evidence metadata.

## Non-negotiable boundaries

- Unknown destination, DNS failure, missing proxy evidence, or expired policy means deny.
- Do not treat Docker's internal network alone as domain-level allowlisting.
- Do not persist authorization headers, query secrets, or response bodies in network logs.
- Build/validation phases that do not require downloads remain offline.

## Acceptance checks

- Unit tests cover private/loopback/link-local/IP-literal denial and exact-host matching.
- Integration tests prove direct DNS/IP bypass fails while an allowed repository succeeds through the proxy.
- Network policy version and decision are attached to workspace evidence.
- Without a runnable enforcement proxy, mark the egress gate incomplete.

