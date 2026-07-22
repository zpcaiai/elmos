---
name: python-engine-contract-and-worker
description: Implement or operate the ELMOS Python modernization engine, shared Engine API, tenant-scoped idempotent jobs, cancellation, evidence emission, and capability-based Legacy, CPU, GPU, Windows, or Notebook Runner routing. Use for Python engine boundary, Worker API, job lifecycle, Runner selection, or control-plane integration work.
---

# Python Engine Contract and Worker

## Preserve authority boundaries

- Keep the Python Worker independently deployable from the Java control plane.
- Reuse `/engine/v1/capabilities`, `scan`, `plan`, `execute-step`, `validate`, job lookup, and cancel.
- Reuse shared tenant, authorization, workflow, Runner lease, usage, audit, Evidence, SCM, delivery, and rollback objects.
- Never import LibCST, mypy, Pyright, pytest, model frameworks, or customer code into the Java control plane.
- Never add PostgreSQL, GitHub, billing, or secret-provider authority to the Python Worker.

## Route by capability

Select exactly one approved profile:

- `PYTHON_LEGACY_LINUX`: Python 2/old glibc baseline capture only.
- `PYTHON_MODERN_CPU`: Python 3.10–3.14, packaging, CST, type, tests, Web, and CPU data/model work.
- `PYTHON_MODERN_GPU`: driver/CUDA/cuDNN/wheel-matched model work.
- `PYTHON_WINDOWS`: pywin32, COM, Office, Windows paths, DLLs, and Windows wheels.
- `PYTHON_NOTEBOOK`: isolated clean-kernel execution and artifact capture.

Deny network by default, expose no control-plane secret, bind the immutable Snapshot, and require image approval evidence before leasing.

## Enforce job semantics

Bind idempotency to organization, operation, key, and immutable input hash. Return the existing result only for identical inputs. Reject key reuse with changed inputs. Scope lookup and cancellation to the owning organization. Do not rewrite terminal jobs. Recover retries through shared lease/attempt fencing rather than a Python-private workflow.

Return explicit Python errors such as `PYTHON_ENVIRONMENT_UNREPRODUCIBLE`, `LEGACY_PYTHON_RUNNER_REQUIRED`, `GPU_RUNNER_REQUIRED`, and `NOTEBOOK_STATE_UNRESOLVED`. Never replace them with generic success.

## Accept completion

Require an independently running Worker, all seven API routes, capability routing, cancellation/idempotency tests, tenant non-disclosure, unified Evidence extensions, and architecture proof that Java does not load Python analysis libraries. Keep external Runner work `NOT_RUN` until observed.

