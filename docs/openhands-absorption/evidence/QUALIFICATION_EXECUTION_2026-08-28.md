# Qualification execution ledger — 2026-08-28

This ledger records bounded local engineering execution only. Every result
below carries `NOT_CERTIFIED` and `NOT_GA`; none is a production certification,
customer acceptance, or independent verification.

| campaign | executed target | result | evidence / remaining gate |
| --- | --- | --- | --- |
| PostgreSQL | disposable PostgreSQL 17.5, named persistent Docker volume, migrations `0001`/`0002`, app role with `NOBYPASSRLS` | `PASS` | 65 events, concurrency 8, p95 113.295 ms, RLS cross-tenant hidden, append-only update/delete rows 0; PostgreSQL failover and independent verification `NOT_RUN` |
| Temporal | Temporal auto-setup 1.29.7 pinned by image digest, real SDK worker replacement and history Replay | `PASS` | worker death followed by replacement activity attempt 2; 64 parent/child history events replayed; multi-node failover `NOT_RUN` |
| production sandbox | Docker `alpine` pinned at `sha256:14358309a308569c32bdc37e2e0e9694be33a9d99e68afb0f5ff33cc1f695dce` | `PASS` (L1 only) | 16 negative checks and orphan cleanup; production L3/L4, secret broker, and independent escape review `NOT_RUN` |
| external Provider | OpenAI Responses, OpenAI Chat Completions, Anthropic-compatible Messages | `FAIL` | OpenAI returned HTTP 429 `insufficient_quota`; compatible endpoint returned HTTP 520; no provider conformance claim made |
| browser/device | Playwright Chromium, Firefox, WebKit plus emulated mobile Chromium | `PASS` (local) | 4 profiles, 3 engines, 0 failed profiles, accessibility/DOM/network/trace/video artifacts; physical device lab and independent verification `NOT_RUN` |
| Golden Repo | Kubernetes `7bf53c7b96b2a155f7812ae93a226069085d08d2`, VS Code `b8f5cda733d36325a6cb477a25bc86f7554ec3a6`, Go `2c7cbba805a3a9c7a9363f5ba72da59104f29fb3` | `PASS` (local) | 12,702,960 measured source LOC, all 3 above 1M; independent holdout and customer acceptance `NOT_RUN` |
| load | disposable PostgreSQL, bounded queue capacity 32, 16 consumers, 256 events | `PASS` (local) | 257 stored events, 0 failures, p95 58.194 ms, 392.023 events/s; active/idle scaling and representative soak `NOT_RUN` |
| Chaos | disposable PostgreSQL/Temporal/Docker targets | `PASS` (local) | 15/15 checks passed, including restart/pause recovery, fencing, RLS, append-only, checkpoint, sandbox cleanup and bounded load; production topology/multi-region DR and independent verification `NOT_RUN` |
| security scan | local Bandit scan of `src/elmos_openhands` | `PASS` (engineering) | 0 high, 0 medium, 30 low findings; independent security review, red team, supply-chain attestation `NOT_RUN` |

The independent review interface is implemented in
`src/elmos_openhands/security_review.py`. It accepts only a separately signed,
digest-bound security report from a distinct `security_reviewer` identity and
returns at most `READY_FOR_EXTERNAL_GATE`; this execution did not supply such a
report, so the security review state remains `NOT_RUN`.

## Reproduction entry points

Use `engines/openhands-absorption-engine/tools/run_qualification_probe.py` with
an explicitly authorized disposable target. The supported probes are
`postgres`, `provider`, `security`, `browser`, `sandbox`, `golden`, `load`, and
`chaos`. The Temporal worker-replacement probe is
`engines/openhands-absorption-engine/tools/run_temporal_probe.py`.

## Release boundary

Local results are self-attested engineering evidence. Real production
Temporal/PostgreSQL topology, production sandbox, external Provider success,
physical browser devices, independent Golden holdout, representative
load/soak, production Chaos, and independent security review remain open.
Overall status therefore remains `NOT_CERTIFIED` / `NOT_GA`; no local result may
be relabeled as production certification or GA.
