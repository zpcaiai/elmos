"""FIX 6, part 3: the intake gate must agree with the model gate.

`intake.create_draft` raises an open question for anything that is not
`many-to-one`, and an open question blocks approval -- so the model-layer
widening is unreachable until intake agrees. Two gates, one rule: keep them
literally the same rule by reusing the model's own canonicalisation.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
PS = "engines/project-synthesis-engine/src/elmos_project_synthesis"


def patch(relative: str, old: str, new: str, *, expect: int = 1) -> None:
    path = ROOT / relative
    src = path.read_text(encoding="utf-8")
    found = src.count(old)
    if found != expect:
        raise SystemExit(f"ABORT {relative}: expected {expect} match(es), found {found}")
    path.write_text(src.replace(old, new, 1), encoding="utf-8")
    print(f"  patched {relative}")


patch(
    f"{PS}/intake.py",
    '''        unsupported_relations = [
            relation
            for relation in normalized_relations
            if relation.get("kind") != "many-to-one"
            or not relation.get("source_field")
            or relation.get("target_field") != "id"
        ]
        adjacency: dict[str, set[str]] = {name: set() for name in entity_names}
        for relation in normalized_relations:
            source = str(relation.get("source", ""))
            target = str(relation.get("target", ""))
            if source in adjacency and target in adjacency:
                adjacency[source].add(target)''',
    '''        # The production profile takes three of the four kinds. `one-to-many`
        # is the same foreign key declared from the other end, so it is judged
        # -- and its cycle contribution counted -- in the canonical orientation,
        # exactly as `models.SynthesisRequest` does. Two gates, one rule.
        def _canonical(relation: dict[str, Any]) -> tuple[str, str, Any, Any]:
            source = str(relation.get("source", ""))
            target = str(relation.get("target", ""))
            source_field = relation.get("source_field")
            target_field = relation.get("target_field")
            if relation.get("kind") == "one-to-many":
                return target, source, target_field, source_field
            return source, target, source_field, target_field

        unsupported_relations = []
        for relation in normalized_relations:
            _, _, canonical_source_field, canonical_target_field = _canonical(relation)
            if (
                relation.get("kind")
                not in {"many-to-one", "one-to-one", "one-to-many"}
                or not canonical_source_field
                or canonical_target_field != "id"
            ):
                unsupported_relations.append(relation)
        adjacency: dict[str, set[str]] = {name: set() for name in entity_names}
        for relation in normalized_relations:
            source, target, _, _ = _canonical(relation)
            if source in adjacency and target in adjacency:
                adjacency[source].add(target)''',
)

patch(
    f"{PS}/intake.py",
    '''                        "PostgreSQL 生产配置仅接受无环的显式 many-to-one 外键，格式必须是 source.field -> target.id。"''',
    '''                        "PostgreSQL 生产配置接受无环的显式 many-to-one / one-to-one / one-to-many 外键，"
                        "格式必须解析为 source.field -> target.id（one-to-many 从另一端声明，"
                        "写作 source.id -> target.field）。many-to-many 需要连接表，尚未支持。"''',
)

print("FIX 6 intake gate applied")
