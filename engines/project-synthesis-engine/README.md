# ELMOS Project Synthesis Engine

The engine turns a bounded natural-language project intent into an approved,
hash-bound requirement baseline and then generates independent Java, Python,
and C# starter projects. Drafting does not generate code; generation requires a
reviewed approval artifact.

## Prerequisites

- Python 3.12–3.14
- `uv` 0.11.16 or a compatible locked runner
- the native Java 21, Python 3.12, and/or .NET 10 toolchain for each selected
  target you intend to verify

```bash
cd engines/project-synthesis-engine
uv sync --locked
```

## 1. Create a reviewable draft

```bash
uv run elmos-project-synthesis draft \
  --name order-service \
  --namespace io.elmos.orders \
  --description 'Create, list, and retrieve orders with a health endpoint.' \
  --entity order \
  --language java \
  --language python \
  --output synthesis-request.json
```

The draft records requirements, acceptance criteria, assumptions, exact target
profiles, and open questions. Names, descriptions, namespaces, target profiles,
and ports are validated before the file is written.

## 2. Review and approve the baseline

Resolve every item in `open_questions` before approval. Approval binds the
reviewed payload to an actor, UTC-capable timestamp, and SHA-256 digest.

```bash
uv run elmos-project-synthesis approve \
  --request synthesis-request.json \
  --actor user:reviewer \
  --output approved-request.json
```

## 3. Generate into a new or engine-owned directory

```bash
uv run elmos-project-synthesis generate \
  --request approved-request.json \
  --output generated/order-service
```

The generator rejects broad output targets, non-empty unmanaged directories,
modified managed files, unsafe paths, invalid manifests, and a changed approved
baseline. Use a new output directory for a materially different approval.

## 4. Run real target verification

```bash
uv run elmos-project-synthesis verify \
  --workspace generated/order-service \
  --evidence verification.json
```

Verification invokes only the selected native toolchains. A missing toolchain,
failed build, failed test, or failed startup probe returns a non-success result.

## Evidence boundary

Generated starters use in-memory persistence and do not enable authentication,
tenant isolation, production secrets, image approval, deployment, SLO, backup,
restore, DR, or certification. Generation status may be `GENERATED`; production
delivery remains `NOT_RUN` and certification remains `NOT_CERTIFIED` until the
separate governed workflows actually run.
