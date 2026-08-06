# Batch 105–108 Cross-Batch Architecture

```text
B104-S16 Real-world Product Certification
    ↓
Batch 105 Modernization Demonstration Golden Routes
    ↓
Batch 106 Polyglot Ephemeral Preview Runtime
    ↓
Batch 107 Live API / Browser / Streaming Validation
    ↓
Batch 108 Evidence PR / Executive / Commercial Certification
```

## Non-negotiable invariants

1. Build/test success never implies runtime success.
2. Runtime READY starts the preview TTL; build time does not consume the ten-minute preview window.
3. A public endpoint is created only for an isolated per-run sandbox and is revoked before compute destruction.
4. Browser/API claims must come from the exact candidate commit and image digest.
5. No certificate trusts a caller-provided `PASS`, `certified`, `destroyed`, or `productionReady` flag.
6. Every level is earned progressively; `PRODUCTION_CANDIDATE` is not an automatic deployment approval.
