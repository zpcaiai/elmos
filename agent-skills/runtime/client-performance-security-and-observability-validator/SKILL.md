---
name: client-performance-security-and-observability-validator
description: Compare client build, bundle, startup, rendering, interaction, network, memory, battery, security, storage, source-map, error handling, and telemetry evidence. Use for frontend quality and release gates.
---

# Client Quality Validation

## Workflow

1. Pin device, CPU, network, browser, cache, fixture, service worker, build mode, image, and version before comparing baseline and target.
2. Measure bundle/chunks/assets/fonts/requests, render, web vitals, route and interaction latency, shifts, long tasks, memory, crash, ANR, battery, and desktop/mobile startup against approved budgets.
3. Scan CSP, XSS sinks, unsafe HTML/eval/scripts, dependencies, source maps, token/cookie/CSRF/CORS/redirects, prototype pollution, postMessage, desktop IPC, WebView, and deep links.
4. Classify local/desktop/mobile storage; reject unencrypted sensitive data without explicit expiring acceptance.
5. Correlate route, screen, error, API, performance, flag, client version, and cohort telemetry to backend traces without passwords, tokens, complete forms, private files, or unauthorized PII.

## Gates

Keep performance, visual, accessibility, and functional decisions independent. Missing baseline, unstable environment, public source maps, secret-bearing telemetry, or exceeded failure budgets block promotion.

## Output

Emit performance comparison, budgets, security/storage findings, source-map policy, error recovery, telemetry contract, and Evidence.
