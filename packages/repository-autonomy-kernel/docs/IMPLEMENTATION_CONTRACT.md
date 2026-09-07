# Autonomy kernel — implementation contract (binding for every capability module)

Package root: `/tmp/ak/packages/autonomy-kernel`
Source root:  `/tmp/ak/packages/autonomy-kernel/src/elmos_autonomy_kernel`
Tests root:   `/tmp/ak/packages/autonomy-kernel/tests`
Spec source:  `/tmp/kernel/elmos-repository-autonomy-kernel-v2.0.0/skills/<skill-id>/`
Run tests:    `cd /tmp/ak/packages/autonomy-kernel && PYTHONPATH=src python3 -m pytest tests/test_<module>.py -q`

## Foundation you build on (READ THESE FIRST — do not modify them)

- `errors.py`      — `KernelError`, `Category`, `register_codes`, `not_applicable`
- `contracts.py`   — `canonical_json`, `digest`, `Status`, `SkillResult`, `Observability`,
                     `require_*` strict decoders, `reject_unknown_fields`, `utc_now`
- `ports.py`       — `Clock`, `EventStore`, `KeyValueStore`, `ArtifactStore`, `LeaseStore`,
                     `RepositoryReader`, `ToolInvoker`, `ProcessRunner`, `ModelProvider`
- `registry.py`    — `DESCRIPTORS` (all 31 declared), `register(skill_id)`, `dispatch`
- `adapters/memory.py`, `adapters/filestore.py` — in-memory + filesystem port implementations

**Never edit a foundation file.** If you need a shared helper that does not exist, put it in
your own module. If you need a new failure code, register it at the top of your own module:

```python
from .errors import Category, KernelError, register_codes
register_codes(Category.SEMANTIC, "MY_STABLE_CODE", "MY_OTHER_CODE")
```

Codes are UPPER_SNAKE and globally unique; re-registering a code under a different category
raises at import time, which is the point.

## Module shape

```python
"""<Capability title>.

<Two to five sentences: what this owns, and — more important — *why* the hard
choice in it is made the way it is. Explain the trap, not the syntax.>
"""

from __future__ import annotations
# stdlib only. NO third-party imports. Python 3.11 target.

from .contracts import ...
from .errors import Category, KernelError, register_codes
from .registry import register

register_codes(Category.X, "CODE_A", "CODE_B")

# ... dataclasses (frozen=True, slots=True) + pure functions + a class if state is needed ...

@register("<skill-id>")
def handle(request: Mapping[str, Any]) -> Mapping[str, Any]:
    """Registry entry point. Decodes strictly, delegates, returns plain outputs."""
```

`handle` returns a plain `Mapping` of outputs on success. On any failure it **raises**
`KernelError` — it never returns an error dict, and never returns `{}` to mean failure.
`dispatch()` turns the raise into the mandated envelope.

## Non-negotiables (these are what "production" means here, and they are tested)

1. **Fail closed.** Unknown input field → `UNKNOWN_FIELD` (use `reject_unknown_fields`).
   Unknown tool/model/policy → deny. Empty policy set → deny. Never "allow because nothing said no".
2. **No silent zero.** 0 is a legal business value (zero cost, zero findings, zero budget left).
   An unmeasured or failed quantity is reported as *unmeasured* (`None` + an explicit
   `"measured": false` flag, or a raise) — never as `0`. This is a real defect class in this
   repository; it has shipped three times.
3. **No floats** in anything hashed, compared, budgeted or persisted. Use `Decimal` or an
   integer of the smallest unit. `canonical_json` rejects floats — do not work around it.
4. **PARTIAL ≠ SUCCEEDED ≠ INTERRUPTED ≠ FAILED.** Never widen one into another.
5. **Determinism.** Same inputs → byte-identical outputs. No `datetime.now()` (inject `Clock`),
   no `random` without an injected seed, no set iteration order in output, no dict ordering luck.
6. **Snapshot / policy staleness is an error**, not a silent refresh.
7. **Secrets never enter** a returned payload, log line, artifact or error message.
8. **Every output that will be cached, compared or signed carries its own `digest(...)`.**

## Docstrings

Every public class and function gets a docstring. Write them for a senior engineer who will
maintain this in two years: state the invariant being protected and the failure it prevents.
Do not narrate the code. Prefer one sharp paragraph over a template of empty sections.

## Tests (`tests/test_<module>.py`)

pytest, stdlib only. You MUST cover, for your skill:

- every `positiveGates` entry in `<spec>/acceptance.yaml` — one test each, named after the gate
- every `negativeTests` entry that is meaningful for your capability — one test each
- every invariant in the `## Non-negotiable invariants` section of `SKILL.md`
- the registry round trip: `dispatch("<skill-id>", good_request).status is Status.SUCCEEDED`
- at least one test proving a *wrong* answer is rejected, not just that a right one is accepted
  (e.g. mutate an input and assert the digest/verification fails)

Tests must not sleep, must not touch the network, and must not depend on wall-clock time
(use `FixedClock`). Use `tmp_path` for filesystem work.

## Style

- `from __future__ import annotations`, full type hints, `dataclass(frozen=True, slots=True)`
- Line length ≤ 100. Ruff rules in force conceptually: E, F, I, B, UP, S (no `assert` in src,
  no `subprocess` with `shell=True`, no bare `except:`).
- Public names in `__all__`.
