# Implementation Guide — Runtime Sandbox and eBPF Behavior Verifier

## Purpose

Enforce and observe filesystem, process, network, syscall, device and resource behavior of untrusted generators, adapters and tools.

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

1. compile syscall/network/path policy
2. run in gVisor/Kata/Firecracker-class isolation
3. observe behavior with eBPF/Falco-class telemetry
4. detect policy escape and covert egress
5. seal violations and terminate safely

## Native acceptance corpus

- `ELMOS_RUNTIME_SANDBOX_EBPF_BEHAVIOR_VERIFIER-01` — native scenario: compile syscall/network/path policy
- `ELMOS_RUNTIME_SANDBOX_EBPF_BEHAVIOR_VERIFIER-02` — native scenario: run in gVisor/Kata/Firecracker-class isolation
- `ELMOS_RUNTIME_SANDBOX_EBPF_BEHAVIOR_VERIFIER-03` — native scenario: observe behavior with eBPF/Falco-class telemetry
- `ELMOS_RUNTIME_SANDBOX_EBPF_BEHAVIOR_VERIFIER-04` — native scenario: detect policy escape and covert egress
- `ELMOS_RUNTIME_SANDBOX_EBPF_BEHAVIOR_VERIFIER-05` — native scenario: seal violations and terminate safely

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
