"""Assert the Rust emitter is `cargo fmt --check` clean across entity shapes.

The generated workspace is gated on `cargo fmt --check`, and rustfmt's line
breaking is a function of how long the caller's entity and field names are.
Hand-tuning the templates against one schema therefore proves nothing. This
script emits several deliberately awkward shapes -- long identifiers, many
fields, every scalar type, both auth modes -- and fails if any of them would
need reformatting.

    uv run --locked python scripts/check_rust_emitter_formatting.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def _cargo() -> str:
    """Resolve cargo to an absolute path before executing it."""
    resolved = shutil.which("cargo")
    if resolved is None:
        raise SystemExit("EXACT_TOOLCHAIN_NOT_AVAILABLE:rust:cargo")
    return resolved

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from elmos_project_synthesis import intake, models  # noqa: E402
from elmos_project_synthesis.rust_production_target import (  # noqa: E402
    render_rust_production,
)

SHAPES: dict[str, tuple[str, tuple[dict[str, object], ...]]] = {
    "short-jwt": (
        "jwt",
        (
            {
                "singular": "order",
                "plural": "orders",
                "fields": [
                    {"name": "reference", "type": "string", "required": True},
                    {"name": "total", "type": "number", "required": True},
                ],
            },
        ),
    ),
    "short-oidc": (
        "oidc",
        (
            {
                "singular": "order",
                "plural": "orders",
                "fields": [
                    {"name": "reference", "type": "string", "required": True},
                    {"name": "total", "type": "number", "required": True},
                ],
            },
        ),
    ),
    "long-names": (
        "jwt",
        (
            {
                "singular": "telemetry_observation",
                "plural": "telemetry_observations",
                "fields": [
                    {
                        "name": "extremely_long_descriptive_identifier",
                        "type": "string",
                        "required": True,
                    },
                    {
                        "name": "measured_quantity_value",
                        "type": "number",
                        "required": True,
                    },
                    {"name": "active", "type": "boolean", "required": False},
                    {"name": "recorded_at", "type": "datetime", "required": False},
                ],
            },
        ),
    ),
    "single-short-field": (
        "oidc",
        (
            {
                "singular": "tag",
                "plural": "tags",
                "fields": [{"name": "label", "type": "string", "required": True}],
            },
        ),
    ),
}


def main() -> int:
    original = models.SUPPORTED_PROFILE_TARGETS
    relaxed = {key: (value | {"rust"}) for key, value in original.items()}
    models.SUPPORTED_PROFILE_TARGETS = relaxed
    intake.SUPPORTED_PROFILE_TARGETS = relaxed
    failures: list[str] = []
    try:
        for label, (auth_mode, entities) in SHAPES.items():
            draft = intake.approve_request(
                intake.create_draft(
                    name=f"enterprise-orders-rust-{auth_mode}",
                    description="Durable authenticated and tenant-isolated order API.",
                    entities=entities,
                    relations=(),
                    permissions=[
                        {
                            "actor": "api_user",
                            "action": action,
                            "resource": entity["singular"],
                            "effect": "allow",
                        }
                        for entity in entities
                        for action in ("create", "read", "update", "delete")
                    ],
                    languages=("rust",),
                    persistence="postgresql",
                    auth_mode=auth_mode,
                ),
                actor="check:rust-formatting",
                approved_at="2026-07-26T00:00:00+00:00",
            )
            files = render_rust_production(
                models.SynthesisRequest.from_mapping(draft), 8088
            )
            directory = Path(tempfile.mkdtemp(prefix="elmos-rust-fmt-"))
            try:
                for relative, content in files.items():
                    destination = directory / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_text(content, encoding="utf-8")
                completed = subprocess.run(  # noqa: S603
                    [_cargo(), "fmt", "--check"],
                    cwd=directory,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if completed.returncode != 0:
                    failures.append(label)
                    print(f"FAILED {label}")
                    print(completed.stdout[:2000])
                else:
                    print(f"ok     {label}")
            finally:
                shutil.rmtree(directory, ignore_errors=True)
    finally:
        models.SUPPORTED_PROFILE_TARGETS = original
        intake.SUPPORTED_PROFILE_TARGETS = original
    if failures:
        print(f"\n{len(failures)} shape(s) would need reformatting")
        return 1
    print("\nall shapes are rustfmt-clean as emitted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
