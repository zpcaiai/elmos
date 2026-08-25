"""ELMOS project-generation spec-surface measurement.

The generation line's emitters are deterministic. So "accuracy" is not the
interesting axis -- what a deterministic emitter emits, it emits exactly.  The
question that decides whether it can produce a real small/medium project is
*how much of a real project's shape the request contract will even accept*, and
whether the emitted output grows with that shape.

This script drives the engine's own intake + generation entry points
(`intake.create_draft`, `intake.approve_request`, `workspace.generate_workspace`)
across the declared request surface and records, per cell, either the exact
rejection code or the real generated file count.

Toolchain note: generation is pure Python and runs anywhere.  The build /
startup / CRUD / RLS verification (`verification.verify_workspace`) needs the
pinned macOS toolchains and is NOT run here -- those cells stay NOT_RUN rather
than being reported as passes.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from elmos_project_synthesis.intake import approve_request, create_draft
from elmos_project_synthesis.models import (
    SUPPORTED_AUTH_MODES,
    SUPPORTED_FIELD_TYPES,
    SUPPORTED_LANGUAGES,
    SUPPORTED_PERSISTENCE,
    SUPPORTED_RELATION_KINDS,
    RequestValidationError,
    SynthesisRequest,
)
from elmos_project_synthesis.workspace import generate_workspace

PLANNED_KINDS = ("fullstack", "worker", "cli", "modular-monolith")


def entity(index: int) -> dict[str, Any]:
    name = f"entity{index}"
    return {
        "singular": name,
        "plural": f"{name}s",
        "fields": [
            {"name": "label", "type": "string", "required": True},
            {"name": "amount", "type": "number", "required": True},
        ],
    }


def permissions(entities: tuple[dict[str, Any], ...]) -> tuple[dict[str, str], ...]:
    return tuple(
        {"actor": "api_user", "action": action, "resource": str(item["singular"]), "effect": "allow"}
        for item in entities
        for action in ("create", "read", "update", "delete")
    )


def build(
    *,
    language: str,
    persistence: str,
    auth_mode: str,
    entity_count: int,
    relations: tuple[dict[str, Any], ...] = (),
) -> dict[str, Any]:
    entities = tuple(entity(i) for i in range(1, entity_count + 1))
    return approve_request(
        create_draft(
            name=f"surface-{language}-{persistence}-{auth_mode}-{entity_count}",
            description="Spec-surface probe for the ELMOS generation contract.",
            entities=entities,
            relations=relations,
            languages=(language,),
            persistence=persistence,
            auth_mode=auth_mode,
            permissions=permissions(entities),
        ),
        actor="measurement:spec-surface",
        approved_at="2026-08-21T00:00:00+00:00",
    )


def outcome(callable_: Any) -> str:
    try:
        callable_()
    except RequestValidationError as error:
        return f"REJECTED:{error}"
    except Exception as error:  # emitter refusal, not a contract rejection
        return f"ERROR:{type(error).__name__}:{str(error)[:120]}"
    return "ACCEPTED"


def generated_file_count(request: dict[str, Any]) -> int | str:
    directory = Path(tempfile.mkdtemp(prefix="elmos-surface-"))
    try:
        manifest = generate_workspace(request, directory / "workspace")
        return int(manifest["file_count"])
    except Exception as error:
        return f"ERROR:{type(error).__name__}:{str(error)[:160]}"
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def main() -> int:
    report: dict[str, Any] = {
        "kind": "elmos.generation-spec-surface-measurement",
        "schema_version": "1.0.0",
        "instruments": {
            "intake": "elmos_project_synthesis.intake.create_draft/approve_request",
            "generation": "elmos_project_synthesis.workspace.generate_workspace",
        },
        "verification_status": {
            "status": "NOT_RUN",
            "reason": (
                "verification.verify_workspace needs the pinned macOS toolchains; "
                "build/startup/CRUD/RLS results are not produced by this run."
            ),
        },
        "declared_surface": {
            "languages": list(SUPPORTED_LANGUAGES),
            "field_types": list(SUPPORTED_FIELD_TYPES),
            "persistence": list(SUPPORTED_PERSISTENCE),
            "auth_modes": list(SUPPORTED_AUTH_MODES),
            "relation_kinds": list(SUPPORTED_RELATION_KINDS),
            "project_kinds_supported": ["api"],
            "project_kinds_planned_but_rejected": list(PLANNED_KINDS),
        },
    }

    # 1. profile combinations: persistence x auth x language
    combinations: dict[str, str] = {}
    for persistence in SUPPORTED_PERSISTENCE:
        for auth_mode in SUPPORTED_AUTH_MODES:
            for language in SUPPORTED_LANGUAGES:
                key = f"{persistence}|{auth_mode}|{language}"
                combinations[key] = outcome(
                    lambda p=persistence, a=auth_mode, l=language: SynthesisRequest.from_mapping(
                        build(language=l, persistence=p, auth_mode=a, entity_count=1),
                        require_approval=True,
                    )
                )
    report["profile_combinations"] = combinations
    report["profile_combination_summary"] = {
        "cells": len(combinations),
        "accepted": sum(1 for v in combinations.values() if v == "ACCEPTED"),
        "codes": dict(Counter(v.split(":", 2)[-1] if v != "ACCEPTED" else "ACCEPTED"
                              for v in combinations.values()).most_common()),
    }

    # 2. entity-count ceiling per language, at the production profile
    entity_scaling: dict[str, Any] = {}
    for language in SUPPORTED_LANGUAGES:
        row: dict[str, Any] = {}
        for count in (1, 2, 3, 5, 10, 20, 21):
            key = str(count)
            try:
                request = build(
                    language=language, persistence="postgresql", auth_mode="jwt", entity_count=count
                )
            except RequestValidationError as error:
                row[key] = f"REJECTED:{error}"
                continue
            except Exception as error:
                row[key] = f"ERROR:{type(error).__name__}"
                continue
            row[key] = generated_file_count(request)
        entity_scaling[language] = row
    report["entity_scaling_postgresql_jwt"] = entity_scaling

    # 3. relation kinds, production vs in-memory profile
    relation_matrix: dict[str, Any] = {}
    entities = (entity(1), entity(2))
    for persistence, auth_mode in (("postgresql", "jwt"), ("in-memory", "none")):
        row: dict[str, str] = {}
        for kind in SUPPORTED_RELATION_KINDS:
            relation = {
                "source": "entity1",
                "target": "entity2",
                "source_field": "label",
                "target_field": "id",
                "kind": kind,
                "required": True,
            }
            row[kind] = outcome(
                lambda k=relation, p=persistence, a=auth_mode: SynthesisRequest.from_mapping(
                    build(
                        language="java", persistence=p, auth_mode=a, entity_count=2, relations=(k,)
                    ),
                    require_approval=True,
                )
            )
        relation_matrix[f"{persistence}|{auth_mode}"] = row
    report["relation_kinds"] = relation_matrix
    del entities

    # 4. project kinds
    kinds: dict[str, str] = {}
    for kind in ("api", *PLANNED_KINDS):
        def attempt(k: str = kind) -> None:
            draft = create_draft(
                name="surface-kind-probe",
                description="Project-kind probe.",
                entities=({"singular": "order", "plural": "orders",
                           "fields": [{"name": "label", "type": "string", "required": True}]},),
                relations=(),
                languages=("java",),
                persistence="in-memory",
                auth_mode="none",
                permissions=(),
            )
            draft = json.loads(json.dumps(draft))
            draft["project"]["kind"] = k
            SynthesisRequest.from_mapping(draft, require_approval=False)

        kinds[kind] = outcome(attempt)
    report["project_kinds"] = kinds

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
