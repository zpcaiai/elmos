---
name: b37-extension-manifest-abi-lifecycle
description: Implement a versioned typed extension manifest ABI capability and lifecycle contract covering identity entrypoints permissions dependencies compatibility activation health shutdown migration and revocation.
---

# Skill 1306: b37-extension-manifest-abi-lifecycle

## Use this skill when

- A stable extension contract or ABI is required.
- Existing plugins use informal manifests or directly link internal implementation classes.

## Domain-specific risks and invariants

- ABI ambiguity causes runtime breakage and unsafe fallback.
- Lifecycle hooks can leak resources or retain credentials after disablement.

## Workflow

1. Inventory all current extension points and private APIs used by plugins.
2. Define canonical extension identity, kind, version, product compatibility, entrypoints, capabilities, permissions, dependencies, configuration schema, data migrations, lifecycle hooks, and evidence outputs.
3. Generate machine-readable manifest and SDK types for every supported language.
4. Implement compatibility negotiation, activation, health, quiesce, shutdown, uninstall, and revocation paths.
5. Add positive and negative ABI fixtures and compatibility tests.

## Required repository outputs

- schemas and generated types for extension manifests
- ABI conformance tests and compatibility matrix
- lifecycle state machine and migration records

## Verification

- Validate manifests against schema and semantic rules.
- Run N-1/N/N+1 compatibility fixtures.
- Verify disable and revoke remove all active capabilities and credentials.

## Stop and escalate when

- An extension depends on an undocumented private API.
- Lifecycle cleanup cannot be proven.
- Compatibility behavior requires silent coercion.

## Definition of done

- All supported extensions use the typed manifest and ABI.
- Breaking changes are versioned and migration paths exist.
- Unknown capability or permission requests are rejected.
