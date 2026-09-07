"""Stable importer binding for the exact repository-orchestrator catalog."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .contracts import ContractError, SelectionSource, require_mapping, require_string
from .dispatcher import DispatchContext, RuntimeDispatcher
from .models import RegistrySnapshot


_DISPATCHER = RuntimeDispatcher()


def build_trusted_context(value: Mapping[str, Any] | None = None) -> DispatchContext:
    """Build host-owned context kept structurally separate from task payloads."""

    raw = require_mapping({} if value is None else value, "trusted_context")
    allowed = {"selection_source", "registry", "approved_journal_root"}
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise ContractError("unknown_trusted_context_field", "unknown trusted context field(s): " + ", ".join(unknown))
    try:
        source = SelectionSource(raw.get("selection_source", SelectionSource.API.value))
    except ValueError as exc:
        raise ContractError("invalid_selection_source", "trusted selection source is invalid") from exc
    registry_value = raw.get("registry")
    registry = None if registry_value is None else RegistrySnapshot.from_payload(require_mapping(registry_value, "trusted_context.registry"))
    root_value = raw.get("approved_journal_root")
    root = None
    if root_value is not None:
        root_text = require_string(root_value, "trusted_context.approved_journal_root")
        candidate = Path(root_text)
        if not candidate.is_absolute():
            raise ContractError("journal_root_not_absolute", "approved journal root must be an absolute path")
        try:
            root = candidate.resolve(strict=True)
        except OSError as exc:
            raise ContractError("journal_root_unavailable", "approved journal root does not exist") from exc
        if not root.is_dir():
            raise ContractError("journal_root_not_directory", "approved journal root must be a directory")
    return DispatchContext(selection_source=source, trusted_registry=registry, approved_journal_root=root)


def dispatch(
    skill_name: str,
    payload: Mapping[str, Any] | None = None,
    *,
    trusted_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Dispatch one exact Skill without invoking providers, SCM, shells, or network."""

    context = build_trusted_context(trusted_context)
    return _DISPATCHER.execute(skill_name, payload, context=context).to_dict()


def handler_names() -> tuple[str, ...]:
    return _DISPATCHER.handler_names


__all__ = ["build_trusted_context", "dispatch", "handler_names"]
