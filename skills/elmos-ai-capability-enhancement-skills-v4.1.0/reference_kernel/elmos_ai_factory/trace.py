from __future__ import annotations
from collections import Counter, defaultdict
from typing import Any, Iterable, Mapping, Sequence

REQUIRED_EVENT_FIELDS = {"id", "type", "sequence", "payloadHash"}

def validate_trace(trace: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    events = trace.get("events")
    if not isinstance(events, list):
        return ["events must be a list"]
    ids: set[str] = set()
    last_sequence = -1
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            errors.append(f"event[{index}] is not an object")
            continue
        missing = REQUIRED_EVENT_FIELDS - set(event)
        if missing:
            errors.append(f"event[{index}] missing {sorted(missing)}")
            continue
        if event["id"] in ids:
            errors.append(f"duplicate event id {event['id']}")
        ids.add(event["id"])
        if not isinstance(event["sequence"], int) or event["sequence"] <= last_sequence:
            errors.append("event sequence must be strictly increasing")
        last_sequence = event["sequence"]
    for event in events:
        if isinstance(event, dict):
            for cause in event.get("causes", []):
                if cause not in ids:
                    errors.append(f"unknown causal event {cause}")
    return errors

def _semantic_counter(events: Iterable[Mapping[str, Any]], ignored_types: set[str]) -> Counter:
    return Counter(
        (e.get("type"), e.get("semanticKey"), e.get("status"))
        for e in events if e.get("type") not in ignored_types
    )

def _side_effect_order(events: Sequence[Mapping[str, Any]]) -> list[str]:
    ordered = sorted(events, key=lambda e: e.get("sequence", -1))
    return [
        str(e.get("semanticKey"))
        for e in ordered if e.get("type") == "side-effect"
    ]

def compare_traces(
    reference: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    ignored_types: set[str] | None = None,
) -> dict[str, Any]:
    ignored = ignored_types or set()
    ref_errors = validate_trace(reference)
    cand_errors = validate_trace(candidate)
    mismatches: list[dict[str, Any]] = []
    if ref_errors:
        mismatches.append({"kind": "invalid-reference", "details": ref_errors})
    if cand_errors:
        mismatches.append({"kind": "invalid-candidate", "details": cand_errors})
    if mismatches:
        return {"equivalent": False, "mismatches": mismatches}

    ref_events = reference["events"]
    cand_events = candidate["events"]
    ref_counter = _semantic_counter(ref_events, ignored)
    cand_counter = _semantic_counter(cand_events, ignored)
    for key in sorted(set(ref_counter) | set(cand_counter), key=str):
        if ref_counter[key] != cand_counter[key]:
            mismatches.append({
                "kind": "semantic-event-count",
                "event": key,
                "reference": ref_counter[key],
                "candidate": cand_counter[key],
            })

    ref_effects = _side_effect_order(ref_events)
    cand_effects = _side_effect_order(cand_events)
    if ref_effects != cand_effects:
        mismatches.append({
            "kind": "side-effect-order",
            "reference": ref_effects,
            "candidate": cand_effects,
        })

    ref_terminal = [e.get("status") for e in ref_events if e.get("type") == "terminal"]
    cand_terminal = [e.get("status") for e in cand_events if e.get("type") == "terminal"]
    if ref_terminal != cand_terminal:
        mismatches.append({
            "kind": "terminal-status",
            "reference": ref_terminal,
            "candidate": cand_terminal,
        })
    return {"equivalent": not mismatches, "mismatches": mismatches}
