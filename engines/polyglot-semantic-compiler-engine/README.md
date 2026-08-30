# ELMOS Polyglot Semantic Compiler Engine

This repository-owned engine binds the 300 exact identities in the pinned
Polyglot Semantic Assurance v3 package to typed, allowlisted runtime entry
points. The attached ZIP is parsed as untrusted data; none of its scripts,
commands, prompts, installers, policies, or Skill bodies are executed.

The local engine provides:

- a digest-bound catalog for 300 Skills, 537 dependency edges, 28 technology
  surfaces, 8 repository surfaces, 784 ordered route cells, and 40 reference
  route plans;
- 297 repository-owned dual-root wrappers plus three digest-bound collision
  bindings that preserve the prior owners byte-for-byte;
- exact tenant/project/actor/revision/environment authority matching;
- durable tenant-isolated idempotency and content-addressed request/result
  artifacts;
- subject-bound external evidence receipts whose canonical digest must be
  verified by the host, with server-owned minimum evidence sets that callers
  cannot weaken;
- bounded repository inventory, planning, model comparison, corpus, proof,
  native-lab, fuzz-result, and quality-gate control-plane operations;
- an opt-in host-authorized external runner for named local toolchains. Each
  profile is strict JSON, uses a private ephemeral sandbox, no shell, a
  sanitized environment, disabled networking, bounded files/stdin/stdout, and
  a process-group timeout. Provider calls use an explicit host adapter
  registry and never inherit credentials or network access;
- conservative service and CLI facades that never manufacture target code,
  native execution, proof, fuzz, independent verification, or certification.

Repository snapshots and content-addressed artifacts use no-follow,
descriptor-anchored reads and verify stable inode metadata before and after
content access. Legacy module APIs are retained only as fail-closed planning or
bounded local-analysis surfaces; they cannot bypass runtime authority or raise
certification state.

## Trust and status boundary

`CODE_COMPLETE_LOCAL_CONTROL_PLANE` describes repository code, not route
qualification. Native language adapters, real source/target toolchains,
representative corpora, provider execution, independent verification, and the
external certification authority remain `NOT_RUN`. Production certification
remains `NOT_CERTIFIED` until those exact evidence gates are executed.

The local runner can execute an explicitly authorized probe or compiler in an
ephemeral sandbox and records a digest-bound, self-attested observation. A
successful process is therefore `EXTERNAL_EXECUTED_UNVERIFIED`, not an
independent receipt. Hosts must independently verify the observation and mint
the receipt digest into `ExecutionAuthority.verified_evidence_digests` before a
quality gate can become `READY_FOR_EXTERNAL_GATE`. Missing binaries,
credentials, customer environments, or independent verifiers are reported as
unavailable rather than inferred as success.

The immutable source package contains a known contract defect: its bundle
Schema admits Batches A-I but its manifest contains Batches A-R. The importer
records that defect and does not rewrite the source or silently treat it as
conformant.

## Local verification

From the repository root:

```sh
make polyglot-semantic-assurance-skills
```

This validates the pinned ZIP and immutable mirror without executing package
content, verifies the compiled catalog and safe dual-root wrappers, and runs
the local fail-closed test suite. It does not run native route labs or certify
any language route.
