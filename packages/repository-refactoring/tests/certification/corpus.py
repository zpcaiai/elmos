"""The Golden corpus: fixture repositories with recorded expected behaviour.

Each entry is a complete, self-contained repository and one Skill invocation
against it.  The recorded expectation is a *digest plus a small set of named
projections*, not a full output dump, for two reasons:

* a digest catches any change at all, which is what a regression suite is for;
* the projections say **what the change was**, so a failure reads as "rename
  stopped following importers" rather than "digest 3f2a… became 91be…".

Recording is deliberately explicit: :func:`record_all` only runs when
``ELMOS_UPDATE_GOLDEN=1``.  A suite that silently re-baselines whatever the
code now does cannot detect a regression — it can only describe one.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from elmos_repository_refactoring.contracts import canonical_json, sha256_payload

GOLDEN_ROOT = Path(__file__).resolve().parents[1] / "golden"
UPDATE_ENV = "ELMOS_UPDATE_GOLDEN"

#: The instant every corpus case runs at.  Any value works; what matters is
#: that it is fixed and supplied through *trusted* context, never the payload.
PINNED_CLOCK = "2026-01-15T09:30:00Z"


def updating() -> bool:
    return os.environ.get(UPDATE_ENV) == "1"


@dataclass(frozen=True, slots=True)
class CorpusCase:
    """One fixture repository, one Skill, one recorded expectation."""

    case_id: str
    skill: str
    description: str
    files: Mapping[str, str]
    payload_extra: Mapping[str, Any] = field(default_factory=dict)
    trusted_context: Mapping[str, Any] = field(default_factory=dict)
    #: Dotted paths into the envelope whose values are recorded verbatim, so a
    #: failure names the behaviour that changed rather than only a digest.
    projections: tuple[str, ...] = ()
    repository_id: str = "corpus"
    revision: str = "c0de" * 10
    #: Some Skills operate on a portfolio, a registry or a set of measurements
    #: rather than on a tree.  Forcing a workspace into their payload would
    #: make them reject it, and a corpus of rejections proves nothing.
    include_workspace: bool = True
    #: Built at collection time from the case itself, so a recorded-evidence
    #: case cannot drift away from the commands the run actually issues.
    executions: Callable[[CorpusCase], list[dict[str, Any]]] | None = None

    @property
    def workspace(self) -> dict[str, Any]:
        return {
            "source": "inline",
            "repository_id": self.repository_id,
            "revision": self.revision,
            "files": [
                {"path": path, "content": content} for path, content in sorted(self.files.items())
            ],
        }

    @property
    def payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = dict(self.payload_extra)
        if self.include_workspace and "workspace" not in payload:
            payload["workspace"] = self.workspace
        return payload

    @property
    def context(self) -> dict[str, Any]:
        """Trusted context, including a pinned clock and any recordings.

        The clock is pinned for every case.  Several Skills timestamp what
        they record — a journal entry, an approval request, an incident
        report — and without a fixed instant those digests change on every
        run, which would make this corpus flaky rather than strict.  Pinning
        it here is also the only way the corpus can assert reproducibility at
        all: "the same input twice" has to include the time.
        """

        resolved: dict[str, Any] = {"now": PINNED_CLOCK, **self.trusted_context}
        if self.executions is not None:
            resolved["recorded_executions"] = self.executions(self)
        return resolved

    @property
    def input_digest(self) -> str:
        """Identity of the *input*, so a changed fixture is never a silent pass."""

        return sha256_payload(
            {"skill": self.skill, "payload": self.payload, "trustedContext": self.context}
        )

    @property
    def golden_path(self) -> Path:
        return GOLDEN_ROOT / f"{self.case_id}.json"


def project(envelope: Mapping[str, Any], path: str) -> Any:
    """Resolve a dotted path, with ``[n]`` indexing, into an envelope.

    Missing is reported as the string ``"<missing>"`` rather than ``None``:
    a projection that silently resolves to null would let a removed field pass
    as an unchanged one.
    """

    current: Any = envelope
    for raw in path.split("."):
        key, _, index = raw.partition("[")
        if key:
            if not isinstance(current, Mapping) or key not in current:
                return "<missing>"
            current = current[key]
        if index:
            position = index.rstrip("]")
            if not isinstance(current, Sequence) or isinstance(current, str | bytes):
                return "<missing>"
            try:
                current = current[int(position)]
            except (IndexError, ValueError):
                return "<missing>"
    return current


def observation(case: CorpusCase, envelope: Mapping[str, Any]) -> dict[str, Any]:
    """What the corpus records for one run."""

    return {
        "caseId": case.case_id,
        "skill": case.skill,
        "description": case.description,
        "inputDigest": case.input_digest,
        "status": envelope.get("status"),
        "riskClass": envelope.get("risk_class"),
        "failureClass": envelope.get("failure_class"),
        "sideEffectsPerformed": envelope.get("side_effects_performed"),
        "reasonCount": len(envelope.get("reasons", ())),
        "outputDigest": sha256_payload(envelope.get("output", {})),
        "evidence": envelope.get("evidence", {}),
        "projections": {path: project(envelope, path) for path in case.projections},
    }


def load(case: CorpusCase) -> dict[str, Any] | None:
    if not case.golden_path.exists():
        return None
    value: dict[str, Any] = json.loads(case.golden_path.read_text(encoding="utf-8"))
    return value


def store(case: CorpusCase, record: Mapping[str, Any]) -> None:
    GOLDEN_ROOT.mkdir(parents=True, exist_ok=True)
    case.golden_path.write_text(
        json.dumps(record, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def describe_difference(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> str:
    """A readable account of what moved, for a failure message."""

    lines: list[str] = []
    for key in sorted(set(expected) | set(actual)):
        left, right = expected.get(key, "<missing>"), actual.get(key, "<missing>")
        if left == right:
            continue
        if key == "projections" and isinstance(left, Mapping) and isinstance(right, Mapping):
            for name in sorted(set(left) | set(right)):
                if left.get(name) != right.get(name):
                    lines.append(
                        f"  projection {name}:\n"
                        f"    was: {canonical_json(left.get(name, '<missing>'))[:400]}\n"
                        f"    now: {canonical_json(right.get(name, '<missing>'))[:400]}"
                    )
            continue
        lines.append(f"  {key}: was {left!r}, now {right!r}")
    return "\n".join(lines) or "  (no field-level difference found)"
