# Test Strategy

## 1. Test evidence contract

Every test run records:

```text
run_id
git commit / package version
skill(s)
environment and reference hardware
fixture versions
command
start/end/elapsed machine wall-clock
result and exit code
P50/P95/P99 where relevant
peak CPU/GPU/memory/disk
provider/model versions
usage and cost
trace/report/artifact locations
known limitations
```

Screenshots or prose without raw machine-readable output are insufficient for backend completion.

## 2. Test pyramid

### Unit

- path normalization and archive resource counters;
- MIME/magic detection;
- token budget math;
- context threshold hysteresis;
- source-anchor serialization;
- idempotency key handling;
- policy precedence;
- manifest digest;
- package diff/rename candidates;
- parser normalization and confidence;
- pricing and ETA feature extraction.

### Contract

- JSON Schema examples;
- OpenAPI request/response;
- event envelope and version compatibility;
- provider adapters;
- object-store and workflow interfaces;
- Skill `contract.yaml` validation;
- model capability snapshots.

### Integration

- upload → object → outbox → workflow;
- scanner → parser sandbox → IR;
- ContentBlock → source anchor → index;
- package manifest → archive extraction → project profile;
- model capability → token accounting → context load plan;
- task checkpoint → process failure → recovery;
- usage receipt → cost ledger reconciliation;
- deletion → derivative/index propagation.

### End-to-end

- multimodal package to downstream Agent;
- folder/ZIP/TAR.GZ project import;
- review corrections/conflict resolution;
- long-context project generation or conversion;
- incremental package update;
- client disconnect/reconnect;
- quarantine/release with authorization;
- model switch and context rebudget;
- full deletion/export.

## 3. Format matrix

| Format | Native | Scanned | Mixed | Encrypted/password | Corrupt | Huge |
|---|---:|---:|---:|---:|---:|---:|
| PDF | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| DOCX/DOC | ✓ | n/a | embedded images | protected as supported | ✓ | ✓ |
| Image | text | handwriting where supported | UI/diagram | n/a | ✓ | tiled |
| Audio | mono/stereo | noisy | multilingual | n/a | ✓ | long |
| Markdown/TXT/LOG | UTF-8 | n/a | code/log/config | n/a | ✓ | streamed |
| ZIP/TAR/TGZ/GZ | ✓ | n/a | nested | ✓ | ✓ | bomb defense |
| Folder | local tree | n/a | multi-root | n/a | changing file | 100k entries |

## 4. Golden multimodal fixtures

Each fixture includes original asset, expected structural blocks, expected anchors and tolerance:

- two-column PDF with footnote and table;
- scanned PDF with rotated pages;
- PDF with native and scanned pages;
- DOCX with tracked changes/comments;
- login UI screenshot;
- architecture diagram with crossing arrows;
- Chinese/English meeting with two speakers;
- Markdown with code, Mermaid and prompt-injection text;
- GBK log with exception stack;
- conflicting PDF/audio/UI requirements.

Golden updates require explicit review and version notes.

## 5. Source provenance tests

- page/bbox opens the correct PDF region;
- audio anchor plays the expected sentence;
- image polygon surrounds expected element;
- Word anchor resolves after correction/versioning;
- TXT line range matches original bytes/encoding;
- code symbol anchor is pinned to package version;
- fused requirement has all supporting/opposing sources;
- deletion invalidates or migrates anchors safely.

Critical source coverage target: 100%.

## 6. Archive security corpus

Use `evals/archive-security-cases.yaml`. Include:

- `../` and deeply encoded variants;
- absolute POSIX path;
- Windows drive and UNC;
- NUL and control characters;
- duplicate/overwriting entries;
- symlink then child path;
- hardlink outside root;
- device/FIFO/socket/setuid;
- sparse file;
- false declared size;
- huge compression ratio;
- millions of tiny entries;
- deep nested archive;
- encrypted archive;
- corrupt central directory/header;
- Unicode/case collision.

Assertion: no host write, no sandbox escape, no uncontrolled resource overshoot.

## 7. Long-context scenario

Use `evals/long-context-scenario.yaml`.

Required conditions:

- corpus estimate ≥2,000,000 tokens;
- active context never exceeds effective input budget;
- P0/P1 pinned;
- ≥3 structured compactions;
- ≥5 exact rehydrations from different anchor types;
- model switch to a smaller context causes a planned partition/compact response;
- service restart and client reconnect;
- actual code/test task completes;
- CriticalFactSet retention 100%;
- no source loss or silent truncation;
- no duplicate provider/tool costs.

## 8. Durable execution fault injection

Inject failure at:

- after object part write, before DB commit;
- after DB commit, before outbox publish;
- after provider accepted request, before receipt persistence;
- before/after external tool side effect;
- during compaction;
- during checkpoint persistence;
- during archive extraction;
- during incremental index swap;
- during deletion propagation;
- queue duplicate/reorder;
- DB failover and object temporary error;
- process `kill -9`.

Validate idempotent result, effect ledger, cost ledger and user-visible status.

## 9. Performance

Declare reference profiles, for example:

```text
small: 4 vCPU / 16 GB
standard: 8 vCPU / 32 GB
gpu-standard: explicit accelerator/model
object/search/database topology
```

Measure:

- 1/10/100 GB upload and resume;
- 1k/10k/100k folder entries;
- ZIP/TAR extraction throughput and early-stop latency;
- PDF pages/minute by type;
- audio realtime factor;
- OCR/ASR accuracy and latency;
- repository symbols/second and graph query P95;
- hybrid retrieval P95;
- context plan, compaction and rehydration P95;
- SSE reconnect and progress lag;
- cost/ETA prediction calibration.

Do not publish performance numbers without fixture, hardware and run count.

## 10. Security

- SAST, dependency and container image scan;
- parser sandbox egress;
- prompt injection tool escalation;
- API authz and object-level access;
- tenant isolation in DB/search/vector/cache/object/event;
- password/secret absence in log/trace/event/provider payload;
- webhook signing/replay;
- rate/quota abuse;
- archive fuzz/property;
- deletion access after completion.

## 11. UI

- keyboard and screen-reader accessibility;
- color-independent security/status indication;
- directory virtualization at 100k entries;
- upload pause/resume/reconnect;
- processing state accuracy;
- correction version diff;
- conflict review;
- context usage category totals;
- partial-ready visibility;
- secret/password telemetry redaction;
- browser memory and responsiveness.

## 12. Quality gates

A release cannot proceed when:

- migration rollback is untested;
- critical source coverage <100%;
- context critical fact retention <100%;
- any cross-tenant leak;
- any archive sandbox escape;
- any secret/password in logs/traces;
- duplicate side effect or billing in recovery tests;
- high-severity dependency vulnerability without accepted mitigation;
- ignored/failed inputs are hidden;
- model capability is unknown but treated as unlimited;
- relevant E2E, performance or security tests are skipped without approval.

## 13. Acceptance report

Use `templates/ACCEPTANCE_REPORT.md`. It must distinguish:

- passed;
- failed;
- blocked;
- not applicable with evidence;
- not run, which means the capability is not complete.
