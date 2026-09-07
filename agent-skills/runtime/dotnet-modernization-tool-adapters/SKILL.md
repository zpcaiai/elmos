---
name: dotnet-modernization-tool-adapters
description: Govern Roslyn, optional GitHub Copilot modernization, deprecated Upgrade Assistant compatibility, and bounded coding-agent adapters without surrendering ELMOS authority.
---

# .NET Modernization Tool Adapters

Roslyn is the deterministic analysis/transformation core. GitHub Copilot modernization is an optional provider. Upgrade Assistant is a deprecated legacy adapter for importing/running historical workflows only. Codex, Claude Code and OpenHands may handle bounded long-tail repair through the existing Agent Gateway.

## Authority matrix

Providers may report assessments, suggestions, patches and tool evidence. They may not select the authoritative target, alter tenant/risk policy, approve security/database changes, judge validation, spend outside budget, accept risk, publish/merge, or mark a migration delivered.

## Adapter workflow

Validate provider/version/capabilities; require an approved organization entitlement and Runner; send the minimum bounded context; attach budget, allowed paths/operations and redaction policy; capture provider/model/tool version and input/output hashes; independently apply and validate candidate patches; route failures through the unified repair loop.

The system must remain functional without a proprietary agent. When Upgrade Assistant is used, label its evidence `DEPRECATED_LEGACY_ADAPTER`, never make the core plan depend on it, and provide the Roslyn/manual fallback.

## Required output

Produce adapter manifest, authority decision, invocation attribution, budget/usage evidence, patch references and independent validation status. Missing provider configuration is `NOT_CONFIGURED`, not a platform failure.
