"""Protocol and adapter negotiation kept outside the orchestration model."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .models import ProtocolCapabilities


class ProtocolNegotiationError(ValueError):
    pass


SUPPORTED_HISTORY_MODES = {"Legacy", "Paginated"}
SUPPORTED_CONSISTENCY = {"eventual", "read-your-writes", "strong"}


@dataclass(frozen=True)
class NegotiatedProtocol:
    history_mode: str
    pagination: bool
    typed_tool_result: bool
    schema_dialect: str
    consistency_model: str
    protocol_version: str
    supports_active_turn_lookup: bool

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def _major(version: str) -> str:
    return version.split(".", 1)[0].lstrip("v")


def negotiate(client: ProtocolCapabilities, server: ProtocolCapabilities) -> NegotiatedProtocol:
    if _major(client.protocol_version) != _major(server.protocol_version):
        raise ProtocolNegotiationError("incompatible protocol major version")
    if client.schema_dialect != server.schema_dialect:
        raise ProtocolNegotiationError("no common schema dialect")
    if server.history_mode not in SUPPORTED_HISTORY_MODES or client.history_mode not in SUPPORTED_HISTORY_MODES:
        raise ProtocolNegotiationError("unsupported history mode")
    if server.consistency_model not in SUPPORTED_CONSISTENCY:
        raise ProtocolNegotiationError("unsupported server consistency model")
    return NegotiatedProtocol(
        history_mode="Paginated" if client.history_mode == server.history_mode == "Paginated" else "Legacy",
        pagination=client.pagination and server.pagination,
        typed_tool_result=client.typed_tool_result and server.typed_tool_result,
        schema_dialect=server.schema_dialect,
        consistency_model=server.consistency_model,
        protocol_version=server.protocol_version,
        supports_active_turn_lookup=client.supports_active_turn_lookup and server.supports_active_turn_lookup,
    )


def locate_active_turn(
    negotiated: Mapping[str, Any] | NegotiatedProtocol,
    paginated_lookup: Callable[[], Any],
    legacy_history: Mapping[str, Any],
) -> Any:
    values = negotiated.to_dict() if isinstance(negotiated, NegotiatedProtocol) else negotiated
    if values.get("history_mode") == "Paginated" and values.get("supports_active_turn_lookup"):
        return paginated_lookup()
    return legacy_history.get("active_turn")
