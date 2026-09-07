# Implementation Guide — Realtime Voice and Multimodal Agent Generator

## Purpose

Generate low-latency audio/video/text agents with session, turn-taking, interruption, tool use, consent, safety and fallback contracts.

## Required vertical slice

A conforming first implementation must execute one real, exact-version vertical slice through:

1. API command and idempotency validation;
2. PostgreSQL run/event/outbox persistence with tenant policy;
3. K7 authority, sandbox, lease and fencing acquisition;
4. the Skill-specific native operation;
5. at least one positive and one negative native fixture;
6. independent proof/evidence production;
7. K8 blocked-or-certified decision;
8. pause/resume and worker-loss recovery;
9. machine wall-clock and cost reporting;
10. safe uninstall/rollback or compensating action.

## Skill-specific work packages

1. compile realtime session and media state machine
2. generate WebRTC/SIP/streaming transport integration
3. handle barge-in, VAD, turn and tool synchronization
4. apply consent, redaction and recording policy
5. measure latency, recovery and degraded text fallback

## Native acceptance corpus

- `ELMOS_REALTIME_VOICE_MULTIMODAL_AGENT_GENERATOR-01` — native scenario: compile realtime session and media state machine
- `ELMOS_REALTIME_VOICE_MULTIMODAL_AGENT_GENERATOR-02` — native scenario: generate WebRTC/SIP/streaming transport integration
- `ELMOS_REALTIME_VOICE_MULTIMODAL_AGENT_GENERATOR-03` — native scenario: handle barge-in, VAD, turn and tool synchronization
- `ELMOS_REALTIME_VOICE_MULTIMODAL_AGENT_GENERATOR-04` — native scenario: apply consent, redaction and recording policy
- `ELMOS_REALTIME_VOICE_MULTIMODAL_AGENT_GENERATOR-05` — native scenario: measure latency, recovery and degraded text fallback

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
