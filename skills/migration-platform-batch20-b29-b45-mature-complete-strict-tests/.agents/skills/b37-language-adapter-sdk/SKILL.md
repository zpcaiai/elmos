---
name: b37-language-adapter-sdk
description: Implement a Language Adapter SDK for parsing semantic extraction PSP/UIR emission source maps diagnostics incremental analysis and conformance without exposing control-plane internals.
---

# Skill 1307: b37-language-adapter-sdk

## Use this skill when

- A new source language or parser must integrate with the migration platform.
- Partners need to implement language adapters independently.

## Domain-specific risks and invariants

- Malformed semantic output can silently corrupt all downstream migration stages.
- Adapters may process highly sensitive source code and require strict local execution.

## Workflow

1. Define adapter input artifacts, workspace model, parser/toolchain invocation, semantic facts, PSP/UIR fragments, diagnostics, source maps, incremental invalidation, and unsupported obligations.
2. Generate SDK interfaces, fixtures, reference adapter, and conformance harness.
3. Require stable symbol identity and deterministic output digests.
4. Execute adapter in sandbox with source-local and no-egress defaults.
5. Test malformed trees, partial code, generated code, mixed versions, cancellation, timeout, and large workspaces.

## Required repository outputs

- language-adapter SDK package and reference implementation
- `PSP/UIR and source-map conformance fixtures`
- adapter capability and version matrix

## Verification

- Run real source toolchains where claimed.
- Compare incremental output with periodic full rebuilds.
- Reject silent semantic drops and unstable identifiers.

## Stop and escalate when

- The parser license or redistribution terms are unclear.
- Stable symbol identity cannot be established.
- Adapter requires source egress not allowed by policy.

## Definition of done

- One external adapter passes conformance and real-workspace tests.
- All unsupported semantics produce obligations.
- Adapter outputs are deterministic and traceable.
