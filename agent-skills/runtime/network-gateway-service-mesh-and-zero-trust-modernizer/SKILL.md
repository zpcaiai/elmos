---
name: network-gateway-service-mesh-and-zero-trust-modernizer
description: Modernize network segmentation, routing, DNS, load balancing, gateways, service mesh, workload identity, mTLS, authorization, egress, and multi-cluster connectivity. Use for infrastructure network and zero-trust planning.
---

# Network and Zero Trust Modernizer

## Network workflow

1. Model physical, virtual network, subnet, routing, firewall, load balancer, gateway, service discovery, mesh, and application-protocol layers separately.
2. Start from minimal connectivity and default deny. Express all ingress, egress, DNS, databases, messaging, observability, and secret-provider flows explicitly.
3. Model L4, HTTP, TCP, TLS, API, internal, and egress gateways independently from service mesh.
4. Replace permanent IP identity with workload identity, mTLS, and authorization where supported, while retaining network policy defense in depth.
5. Choose no mesh, sidecar, ambient, gateway-only, or library-based operation from service count, protocol, performance, team readiness, and security needs.
6. Classify every egress as approved, conditional, proxy-required, private-link-required, blocked, or unknown.
7. Validate DNS, TCP, TLS, HTTP, gRPC, MTU, latency, bandwidth, loss, failover, firewall, and actual policy enforcement.
8. Preserve TTL, resolver and negative caches, split horizon, old endpoints, health checks, and rollback for DNS changes.

Mesh is optional. Treat version-specific ambient and L7 behavior as compatibility evidence, not an assumption. Never widen public access automatically.

