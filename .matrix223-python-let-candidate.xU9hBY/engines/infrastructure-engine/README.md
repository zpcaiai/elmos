# ELMOS Infrastructure Engine

This independently deployable Java 21 worker implements the Batch 16 cloud and infrastructure domain contract. It models four modernization tracks, canonical provider-neutral resources, deterministic placement and safety policies, plan-first mutation gates, cutover adjudication, and shared ELMOS evidence mappings.

The repository ships no live cloud, hypervisor, SSH, WinRM, OpenTofu, Kubernetes, serverless, observability, cost, or chaos credential. Every external Runner is `NOT_CONFIGURED`; scan, validation, provisioning, apply, traffic, DNS, chaos, and deletion requests therefore fail closed with empty evidence. A generated image, manifest, IaC plan, or policy decision is never represented as external execution.
