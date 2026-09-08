# AI External Execution and Production Certification Gate

## Purpose

This gate separates four facts that must not be collapsed:

1. a provider is configured;
2. a real operation was executed;
3. a different actor verified immutable evidence from that operation;
4. an independently trusted certifier signed the exact complete evidence set.

Local tests can validate the contract, but cannot manufacture any of those
external facts. `UNKNOWN`, `FAIL`, `NOT_RUN`, and `NOT_CONFIGURED` all block
production certification.

## Safe preflight

The checked-in plan contains environment-variable names only. It does not
contain credentials and the preflight performs no network or provider action:

```sh
make ai-external-gate-preflight
```

The repository template is expected to report `BLOCKED` until all exact
provider, corpus, deployment, and certifier bindings are supplied. The Make
target treats that expected fail-closed result as a successfully validated
template; remove `--expect-blocked` when an operator needs readiness to be a
hard gate.

## Evidence report

Every required operation must record one of `PASS`, `FAIL`, `UNKNOWN`,
`NOT_RUN`, or `NOT_CONFIGURED`. A `PASS` additionally requires:

- a non-synthetic evidence file below the selected evidence root;
- the exact SHA-256 of that file;
- distinct executor and verifier actors;
- the authorization identifier for that exact operation;
- the evidence role declared in the plan.

Evidence paths are repository-relative POSIX paths below the evidence root.
Absolute paths, traversal, symlinks, missing files, and digest mismatches fail
closed.

Validate a report and show its blockers without a certificate:

```sh
PYTHONPATH=packages/repository-orchestrator/src \
uv run --project packages/repository-orchestrator --locked --group test \
elmos-repository-orchestrator external-certify \
  --plan packages/repository-orchestrator/config/ai-external-gate-plan.json \
  --report docs/ai-modernization/external-execution-report-20260908.json \
  --evidence-root docs/ai-modernization
```

An uncertain provider result is never retried blindly. Reconcile it using the
provider's operation/request identifier, then append new evidence under a new
authorized execution record.

## Independent certificate

Certification is possible only when all ten operations are `PASS` and an
independent certificate binds all of the following:

- gate ID, exact repository revision, and artifact digest;
- canonical report digest and canonical evidence-set digest;
- certifier actor and organization;
- fresh certification and expiry timestamps;
- the public-key digest pinned in the plan;
- a valid detached `SHA256_WITH_PEM_KEY` signature.

Run the same `external-certify` command with `--certificate` and
`--public-key`. The producer cannot predeclare certification, the certifier
cannot equal the producer, and a placeholder trust root is rejected.

## Current external result

The 2026-09-08 bounded live run found no exact Elasticsearch or Dify Vercel
integration or configured binding. OpenAI model inventory returned HTTP 200,
but the single authorized generation attempt returned HTTP 429 and remains
`UNKNOWN`. Gemini inventory and generation returned HTTP 400 and are `FAIL`.
No Elasticsearch, Dify, collector, multimodal, representative production
workload, deployment, or independent-certifier execution was available.

Therefore the current report is valid evidence of a blocked gate, not evidence
of completion: external operations are not all `PASS`, and production remains
`NOT_CERTIFIED`.
