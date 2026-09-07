---
name: elmos-provider-prompt-cache-adapters
description: Implement versioned OpenAI, Anthropic, and self-hosted prompt-prefix cache adapters with capability discovery, exact accounting, safe fallback, and provider-isolated namespaces.
version: 1.2.0
package: elmos-build-cache-staging-codex-claude-parity
phase: P8-parity-foundation
dependencies: [elmos-cache-api-cli-contracts, elmos-cache-security-provenance, elmos-cache-observability-performance]
---

# Provider Prompt Cache Adapters

## Outcome

Create one provider-neutral contract that exploits each model runtime’s exact-prefix or prefix-KV reuse without confusing provider caches with ELMOS Action Cache. This is an implementation skill. The coding agent must inspect and modify the actual ELMOS repository, run reproducible verification, and attach evidence. A design document, mocked counter, or isolated demo is not completion.

## Use this skill when

- Adding or changing an OpenAI, Anthropic, compatible gateway, vLLM, SGLang, or other model-provider integration.
- Prompt-cache hit rates are low, provider usage counters are missing, or model/effort/tool changes cause unexplained misses.
- Implementing phase `P8-parity-foundation` after deterministic cache correctness and provenance are already in place.

## Required inputs

- Current ELMOS model gateway, request builders, provider SDK versions, retry logic, tenant isolation, and observability.
- Provider capability profiles covering cache keys, breakpoints, TTL choices, usage counters, request limits, and model/version compatibility.
- Canonical Prompt Prefix Manifest and Prompt Cache Namespace schema from this package.
- Fresh evidence from dependency skills and a test account or deterministic fake provider for every enabled adapter.

## Produced artifacts

- `PromptCacheProviderAdapter` SPI and implementations for OpenAI, Anthropic, and configured self-hosted runtimes.
- Versioned capability registry with `SUPPORTED`, `DEGRADED`, and `DISABLED` states rather than hard-coded provider assumptions.
- Provider-specific request mapping, response usage normalization, error taxonomy, circuit breaker, and no-cache fallback.
- Per-request `PromptCacheObservation` linking stable-prefix digest, namespace, cache-read/write tokens, TTL class, routing key, model, effort, and reason codes.
- Contract, integration, replay, security, and SDK-compatibility tests.

## Non-negotiable invariants

- Prompt cache reuse is exact-prefix reuse only; semantic similarity never counts as a provider prompt-cache hit.
- Provider, account/project, region when relevant, model snapshot, effort/reasoning profile, tool-schema digest, and stable-prefix digest partition the namespace.
- Provider cache keys never replace tenant authorization, ActionKey validation, CAS digest verification, or validation evidence.
- Unknown or changed provider capabilities fail to safe no-cache behavior; they never silently emit fabricated hit counters.
- Raw secrets, credentials, full source code, and user content are not written into telemetry labels or shared cache keys.
- Retries preserve idempotency and the intended cache identity while preventing duplicate accounting.

## Execution workflow

1. Inventory every model request path and classify it as conversational generation, deterministic conversion, repair, test generation, summarization, or one-shot execution.
2. Implement the provider-neutral request/response types and capability negotiation before adding provider-specific fields.
3. Add OpenAI, Anthropic, and self-hosted adapters behind feature flags and validate each against recorded fixtures and live sandbox calls when credentials exist.
4. Normalize provider usage into eligible input tokens, cache-write tokens, cache-read tokens, uncached input tokens, output tokens, TTL class, and miss reason.
5. Run stable-prefix, model-switch, effort-switch, tool-change, TTL-expiry, retry, streaming, and provider-outage tests.
6. Enable observations first, then cache hints/keys, then explicit breakpoints or long-lived TTL modes only after cost and correctness gates pass.

## Implementation tasks

1. Define `PromptCacheRequest`, `PromptCacheHint`, `ProviderCapabilityProfile`, `PromptCacheObservation`, and `NormalizedTokenUsage` with forward-compatible unknown fields.
2. Implement OpenAI mapping for stable prompt-cache routing keys, supported explicit cache breakpoints, cached-token and cache-write usage fields, and model-specific capability discovery.
3. Implement Anthropic mapping for automatic or explicit cache control, supported TTL classes, content-block breakpoints, cache read/write usage, and model/effort partitioning.
4. Implement self-hosted prefix-KV mapping with replica identity, block-hash compatibility, tokenizer/model build digest, cache-aware routing, and eviction visibility.
5. Add provider profile pinning so SDK or API upgrades require a compatibility test and explicit profile transition.
6. Expose structured miss reasons including `MODEL_CHANGED`, `EFFORT_CHANGED`, `TOOL_SCHEMA_CHANGED`, `PREFIX_CHANGED`, `TTL_EXPIRED`, `WRONG_REPLICA`, and `PROVIDER_UNSUPPORTED`.
7. Add cost accounting that distinguishes provider prompt-cache savings from ELMOS exact Action Cache savings and avoids double counting.
8. Add a kill switch per provider, model family, tenant cohort, and request class.

## Acceptance criteria

- All enabled adapters pass the same contract suite and preserve a byte-identical canonical stable prefix for identical inputs.
- Usage reconciliation error is zero for deterministic fixtures and no more than 0.5% for aggregated live-provider samples after documented rounding.
- A provider capability or SDK mismatch causes explicit degraded/no-cache mode and an alert, not a malformed production request.
- Model, effort, tool-schema, and tenant changes produce the expected namespace split in 100% of test cases.
- No provider cache observation can authorize retrieval of another tenant’s prompt, artifact, or model result.
- Every request is attributable to one cache mode and one miss/hit reason without double-counting tokens.

## Evidence required

- Adapter source paths, API/SDK versions, capability-profile digest, and model matrix.
- Contract-test and live-sandbox test commands with pass/fail counts and redacted request/response fixtures.
- Token-accounting reconciliation report, namespace-isolation tests, failure-mode traces, and kill-switch exercise.
- Before/after cache-read ratio and provider cost for a fixed stable-conversation corpus.

## Anti-patterns

- Assuming all providers expose the same cache controls, TTLs, counters, or routing semantics.
- Calling a repeated model answer an Action Cache hit when only the prompt prefix was reused.
- Putting tenant identifiers, secrets, timestamps, random run IDs, or mutable paths into the stable prefix or high-cardinality metric labels.
- Changing model, effort, tool order, or system instructions without an explicit namespace transition.
- Claiming a hit based only on latency instead of provider usage evidence.

## Done condition

The skill is complete only when provider adapters, versioned capability profiles, normalized accounting, isolation controls, contract/live tests, feature flags, dashboards, and rollback evidence exist in the ELMOS repository and `./validate.sh` passes.
