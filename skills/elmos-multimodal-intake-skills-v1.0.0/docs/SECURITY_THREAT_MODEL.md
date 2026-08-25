# Security Threat Model

## 1. Assets

- Original user documents, media, source code and archives;
- decrypted temporary content and passwords;
- OCR/ASR/transcription and derived Content IR;
- secrets, PII, proprietary code and production configurations;
- tenant/project ACL and model access policies;
- task checkpoints, tool receipts and cost ledger;
- parser/provider credentials and signing keys;
- repository map, symbols and project memory;
- audit trail and deletion evidence.

## 2. Adversaries

- Malicious uploader;
- compromised tenant account;
- document/website content attempting prompt injection;
- malicious dependency or parser library;
- compromised OCR/ASR/model provider;
- cross-tenant attacker;
- curious or overprivileged employee/service;
- malformed archive designed for sandbox escape or resource exhaustion;
- accidental user error, stale version or misconfigured policy.

## 3. Trust assumptions

- All user bytes and extracted text are hostile until classified.
- File metadata, MIME, declared archive sizes and paths can lie.
- Model output can be incorrect or manipulated.
- Queue delivery can duplicate and reorder.
- clients disconnect and retry.
- providers can change model aliases/capabilities.
- logs and traces are a data-exfiltration surface.
- ignore files and project configuration are not security policy.

## 4. Threats and controls

| ID | Threat | Primary controls | Required evidence |
|---|---|---|---|
| T01 | Extension/MIME spoofing | magic + structure validation, allowlist | fixture and scanner logs |
| T02 | Malware in Office/PDF/binary | AV, macro/script detection, quarantine | malicious corpus pass |
| T03 | Parser RCE | no-network sandbox, seccomp/container/VM, read-only base, resource limits | escape test, image/SBOM |
| T04 | PDF JS/Office macro execution | parser flags, static inspection, separate converters | execution canary remains untouched |
| T05 | Prompt injection in text/image/audio | data/instruction channel separation, tool gateway authz | adversarial eval |
| T06 | ZIP Slip/path traversal | fd/handle-relative safe extraction, canonical validation | traversal corpus |
| T07 | Compression bomb | streamed actual counters, cumulative limits, early stop | node resource graph |
| T08 | Symlink/hardlink escape | do not create/follow by default, link-chain validation | link attack cases |
| T09 | Special file creation | block device/FIFO/socket/setuid | filesystem audit |
| T10 | Nested archive budget reset | shared global extraction budget | nested bomb case |
| T11 | Password leakage | ephemeral secret handle, redaction, no telemetry | log/DB/trace scan |
| T12 | Secret leakage to model | secret scanner, model access policy, masking | provider payload audit |
| T13 | Cross-tenant object/index leak | tenant keys/RLS/namespace + tests | cross-tenant negative tests |
| T14 | Stale/wrong project version | immutable package versions, task pinning | version-switch test |
| T15 | Silent context loss | CriticalFactSet and integrity gates | long-context report |
| T16 | Duplicate external effect | idempotency key + effect ledger + receipt reconcile | fault injection |
| T17 | Duplicate billing | provider request id uniqueness, usage reconciliation | ledger test |
| T18 | Webhook spoof/replay | signature, nonce/delivery id, time window | replay test |
| T19 | SSRF through parser/link | no egress or strict provider proxy | egress test |
| T20 | Storage exhaustion | tenant quotas, reservations, early archive limits, cleanup | quota stress |
| T21 | Toxic file names/terminal escape | safe encoding/display, no shell interpolation | filename corpus |
| T22 | Log injection/content leak | structured logs, content minimization, sanitization | log inspection |
| T23 | Provider data residency violation | routing policy and region allowlist | routing decision audit |
| T24 | Malicious ignore rule hides risk | security decisions outrank analysis rules | policy precedence test |
| T25 | Supply-chain compromise | pinned deps, SBOM, signatures, vulnerability SLA | build provenance |
| T26 | Deletion incomplete | lineage graph, deletion jobs, reconciliation | deletion proof |
| T27 | Privilege escalation by document | tool schema allowlist, parameter constraints, approval | red-team scenario |
| T28 | Model capability spoof/staleness | trusted source, expiry, conservative fallback | capability drift test |

## 5. Archive extraction algorithm requirements

Use handle-relative operations where the platform supports them:

1. Open a newly created sandbox root directory handle.
2. Decode the archive entry name with strict error handling.
3. Reject NUL, absolute, drive-letter and UNC paths.
4. Split into components; reject empty/`.`/`..` escape semantics after normalization.
5. Walk/create parent directories relative to the sandbox handle without following links.
6. Revalidate type and resource limits immediately before write.
7. Create a new file without following links and without overwriting by default.
8. Stream bytes while counting actual output.
9. Verify output size/hash and close.
10. Record decision and source entry.
11. Atomically publish only after the whole extraction passes the package policy.

A string `startsWith(rootPath)` check is insufficient.

## 6. Sandbox baseline

A parser/extractor worker should have:

- isolated user/namespace or microVM;
- no host mounts;
- read-only runtime image;
- one read-only input handle and capped scratch output;
- no network by default;
- no cloud metadata endpoint;
- no Docker socket;
- no inherited provider credentials;
- low process/file-descriptor limits;
- CPU, memory, disk and wall-clock quotas;
- syscall restrictions where available;
- deterministic cleanup;
- image digest and SBOM recorded with run.

OCR/ASR provider calls should go through a separate proxy that sends only the approved content and records routing policy.

## 7. Prompt injection boundary

The system should represent content as:

```json
{
  "channel": "untrusted_content",
  "source_anchor": "...",
  "text": "Ignore all previous instructions..."
}
```

It must never concatenate content into system/developer instructions. The model may summarize or classify the text, but tool execution is decided by:

1. trusted task intent;
2. authenticated user authorization;
3. project/tenant policy;
4. tool allowlist;
5. parameter validation;
6. risk classification;
7. optional human approval;
8. idempotency/compensation ability.

No document can grant itself permissions.

## 8. Secret and PII handling

### Detection

- common private-key headers;
- `.env` and configuration patterns;
- cloud/API token signatures;
- database URLs and credentials;
- high-entropy values with context;
- certificates and keystores;
- PII classifiers appropriate to region.

### Handling

- keep raw bytes in encrypted restricted storage;
- derived text replaces value with a stable redaction token;
- provide variable name/type/use to the model, not value;
- require explicit authorized reveal in a constrained tool if operationally necessary;
- never put secrets in prompts, logs, metrics, trace attributes or events;
- rotate credentials when accidental exposure is detected.

## 9. Authorization matrix

At minimum authorize independently:

- upload/read/delete original asset;
- view unredacted content;
- provide archive/PDF password;
- release quarantine;
- change analysis view;
- permit third-party provider;
- start high-cost processing;
- start code execution;
- approve high-risk tool action;
- rebase running task to a new package version;
- restore checkpoint;
- export project memory/audit;
- place/remove retention hold.

## 10. Audit

Audit events should include actor, tenant/project, action, object/version, decision, policy version, time, trace and safe metadata. Do not store raw document text or secret values.

High-value events:

- access to unredacted content;
- password submission;
- quarantine release;
- provider routing override;
- tool approval;
- task restore/replay;
- context integrity exception;
- retention/deletion/hold;
- model capability admin override;
- billing adjustment.

## 11. Security testing

Required families:

- malicious file corpus;
- parser fuzzing;
- archive property tests;
- sandbox escape and egress tests;
- prompt-injection and tool escalation tests;
- cross-tenant/storage/index/cache isolation;
- secret redaction in prompt/log/event/trace;
- webhook replay/signature;
- idempotency/duplicate billing;
- dependency/SBOM and image scanning;
- backup restore permissions;
- deletion propagation.

## 12. Incident response

1. Quarantine affected assets/package versions.
2. Stop vulnerable parser/provider route with a feature flag.
3. Preserve minimal forensic evidence and audit chain.
4. Identify tenants/tasks/derived indexes exposed.
5. Rotate affected credentials.
6. Patch image/dependency/policy and rerun malicious fixtures.
7. Reprocess affected content if safe.
8. notify according to policy/law.
9. document root cause and add a permanent regression test.

## 13. Secure defaults

- deny provider egress unless approved;
- deny encrypted content processing until password is provided through secret channel;
- deny unsafe archive entry;
- do not follow links;
- do not overwrite existing extracted paths;
- do not execute content;
- quarantine on high-severity uncertainty;
- redact secrets before model routing;
- reject unknown model capacity rather than assuming large context;
- block high-risk task when context integrity fails.
