"""Generate templates/rust/Cargo.production.lock from the emitted manifest.

The lock must be produced by the exact manifest the emitter writes -- a
hand-approximated probe crate resolves a different dependency graph, and
``cargo build --locked`` then fails on a lock that looks plausible. This script
emits a real production workspace with the lock check stubbed out, runs
``cargo generate-lockfile`` inside it, and writes the result back as the
template with the project name replaced by the substitution marker.

Run it after changing any dependency in ``rust_production_target.py``:

    uv run --locked python scripts/bootstrap_rust_production_lock.py
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

from elmos_project_synthesis import intake, models, rust_production_target  # noqa: E402
from elmos_project_synthesis.intake import approve_request, create_draft  # noqa: E402

PLACEHOLDER = "# placeholder replaced by cargo generate-lockfile\nversion = 4\n"
MARKER = "__ELMOS_PROJECT_NAME__"
PROJECT = "enterprise-orders-rust-jwt"


def main() -> int:
    template_path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "elmos_project_synthesis"
        / "templates"
        / "rust"
        / "Cargo.production.lock"
    )
    # The profile gate only opens for a target once that target has produced
    # integration evidence, and producing that evidence requires emitting the
    # workspace this script is here to build. The gate is therefore relaxed for
    # this bootstrap process only -- the committed table is untouched, so the
    # product path still refuses rust until the acceptance actually passes.
    original_targets = models.SUPPORTED_PROFILE_TARGETS
    relaxed = {key: (value | {"rust"}) for key, value in original_targets.items()}
    models.SUPPORTED_PROFILE_TARGETS = relaxed
    intake.SUPPORTED_PROFILE_TARGETS = relaxed
    original = rust_production_target._production_lock
    rust_production_target._production_lock = lambda _project: PLACEHOLDER
    try:
        request = approve_request(
            create_draft(
                name=PROJECT,
                description="Durable authenticated and tenant-isolated order API.",
                entities=(
                    {
                        "singular": "order",
                        "plural": "orders",
                        "fields": [
                            {"name": "reference", "type": "string", "required": True},
                            {"name": "total", "type": "number", "required": True},
                        ],
                    },
                ),
                relations=(),
                languages=("rust",),
                persistence="postgresql",
                auth_mode="jwt",
            ),
            actor="bootstrap:rust-production-lock",
            approved_at="2026-07-26T00:00:00+00:00",
        )
        files = rust_production_target.render_rust_production(
            models.SynthesisRequest.from_mapping(request), 8088
        )
    finally:
        rust_production_target._production_lock = original
        models.SUPPORTED_PROFILE_TARGETS = original_targets
        intake.SUPPORTED_PROFILE_TARGETS = original_targets

    temporary = Path(tempfile.mkdtemp(prefix="elmos-rust-lock-"))
    try:
        for relative, content in files.items():
            destination = temporary / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8")
        completed = subprocess.run(  # noqa: S603
            [_cargo(), "generate-lockfile"],
            cwd=temporary,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            sys.stderr.write(completed.stdout + completed.stderr)
            return 1
        lock = (temporary / "Cargo.lock").read_text(encoding="utf-8")
        if f'name = "{PROJECT}"' not in lock:
            sys.stderr.write("generated lock does not name the project\n")
            return 1
        template_path.parent.mkdir(parents=True, exist_ok=True)
        template_path.write_text(lock.replace(PROJECT, MARKER), encoding="utf-8")
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
    print(f"wrote {template_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
