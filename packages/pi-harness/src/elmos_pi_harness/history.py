"""History SPI with bounded pagination and active-turn compatibility."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any


def paginate(items: Sequence[Mapping[str, Any]], *, offset: int = 0, limit: int = 100) -> dict[str, Any]:
    if offset < 0 or not 1 <= limit <= 1000:
        raise ValueError("invalid history pagination")
    page = list(items[offset : offset + limit])
    next_offset = offset + len(page) if offset + len(page) < len(items) else None
    return {"items": page, "next_offset": next_offset, "consistency": "read-your-writes"}


def locate_active_turn(capabilities: Mapping[str, Any], paginated_lookup: Callable[[], Any], legacy_history: Mapping[str, Any]) -> Any:
    if capabilities.get("history_mode") == "Paginated" and capabilities.get("supports_active_turn_lookup"):
        return paginated_lookup()
    return legacy_history.get("active_turn")
