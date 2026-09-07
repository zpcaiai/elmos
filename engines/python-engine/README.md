# ELMOS Python Engine

The Python 3.14 Worker is ELMOS's third language engine. It implements the shared `/engine/v1` API while keeping tenant authority, workflow, Runner leases, billing, audit, SCM, delivery, and rollback in the Java control plane.

Its repository-verifiable core includes safe Python project/environment discovery, lock reproducibility analysis, capability-matched Runner routing, LibCST plus CPython AST semantic graphs, three-path target planning, bounded idempotent Codemods, Python 2 semantic-risk and packaging/native-ABI analysis, Django/Flask advisors, pipeline/notebook profiles, executable-model artifact quarantine, numerical/data comparison, path-specific independent validation, and content-addressed Python Evidence extensions.

Run locally with Python 3.14.6 and the committed uv lock:

```bash
/opt/homebrew/bin/uv sync --locked --python /opt/homebrew/bin/python3.14
/opt/homebrew/bin/uv run --locked pytest
/opt/homebrew/bin/uv run --locked ruff check src tests
/opt/homebrew/bin/uv run --locked mypy src
ELMOS_PYTHON_WORKSPACE_ROOT="$PWD/test-fixtures/scenarios" \
  /opt/homebrew/bin/uv run --locked uvicorn elmos_python.worker.main:app --port 8087
```

Static scan never executes setup files, imports customer modules, follows workspace symlinks, or loads pickle/joblib/checkpoints. Dynamic dependency resolution, type checking, tests, runtime tracing, legacy Python, notebooks, GPU workloads, Windows behavior, and model loading require an approved capability-matched sandbox and remain `NOT_RUN` otherwise.

The evidence boundary and exact local checks are recorded in [`docs/batch-12-verification.md`](../../docs/batch-12-verification.md).
