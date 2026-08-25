# Official Coding-Agent Cache Mechanisms Used as Design Inputs

Reviewed: 2026-08-20

This note records public mechanisms, not a vendor-wide hit-rate benchmark.

## OpenAI API prompt caching

Official documentation describes exact prefix reuse for eligible prompts, recommends placing static instructions/tool definitions before variable content, exposes cached-token usage, supports stable prompt-cache routing keys, and documents explicit cache breakpoints for supported models. ELMOS maps these features through a versioned provider adapter and does not assume support across all models or API versions.

Official source:
- https://developers.openai.com/api/docs/guides/prompt-caching
- https://developers.openai.com/api/docs/guides/production-best-practices

## Codex cloud environments

Official Codex documentation describes cached container state and invalidation when initialization-relevant inputs change. The public changelog has also described major median startup improvement from container caching. ELMOS uses this only as architectural evidence for precise environment snapshots; it does not copy a vendor result into an ELMOS performance claim.

Official source:
- https://developers.openai.com/codex/cloud/environments
- https://developers.openai.com/codex/changelog

## Anthropic prompt caching and Claude Code

Official Anthropic documentation describes automatic and explicit prompt caching, cache ordering across tools/system/messages, supported TTL choices, usage counters, and exact growing-prefix behavior in Claude Code. Model, effort, tool, and system-context changes can partition or invalidate reuse. ELMOS therefore maintains provider/model/effort/tool/prefix compatibility identities and an append-only context ledger.

Official source:
- https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching
- https://docs.anthropic.com/en/docs/claude-code/prompt-caching

## Design conclusion

High coding-agent cache effectiveness is a system property:

```text
stable canonical prefix
+ append-only task/repository context
+ provider-aware routing and accounting
+ exact deterministic Action reuse
+ precise incremental invalidation
+ warm environment/dependency snapshots
+ locality-aware scheduling
+ durable checkpoints/staging
+ miss explainability and SLO rollback
```

No public source above defines one universal Codex or Claude Code end-to-end cache hit percentage. ELMOS parity must be measured on declared scenarios with its own telemetry and zero-false-hit gate.
