"""FIX 6, part 2: point the generation sites at the canonical relation orientation.

Kept in its own file only because it was authored after `apply_fixes.py`; it
follows the same discipline -- every replacement asserts an exact match count
first, so a silent no-op is impossible when upstream has moved.
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
    f"{PS}/models.py",
    """    @property
    def entity(self) -> EntitySpec:
        return self.entities[0]""",
    '''    @property
    def canonical_relations(self) -> tuple[RelationSpec, ...]:
        """Every relation with its foreign key on `source`, referencing `target.id`.

        Generation reads this rather than `relations`, so emitters keep one code
        path no matter which end the author declared the relation from.
        Documentation keeps reading `relations`, because an ER diagram has to
        show what was written.
        """

        return tuple(relation.canonical() for relation in self.relations)

    @property
    def entity(self) -> EntitySpec:
        return self.entities[0]''',
)

patch(
    f"{PS}/production_profile.py",
    """    uuid_relation_fields = {
        (relation.source, relation.source_field)
        for relation in request.relations
        if relation.source_field is not None and relation.target_field == "id"
    }""",
    """    uuid_relation_fields = {
        (relation.source, relation.source_field)
        for relation in request.canonical_relations
        if relation.source_field is not None and relation.target_field == "id"
    }""",
)

patch(
    f"{PS}/production_profile.py",
    """    for relation in request.relations:
        if relation.source_field is None or relation.target_field is None:
            continue""",
    """    for relation in request.canonical_relations:
        if relation.source_field is None or relation.target_field is None:
            continue""",
)

patch(
    f"{PS}/production_profile.py",
    """                f'  REFERENCES "app"."{target_table}" ("tenant_id", "{relation.target_field}")',
                "  ON UPDATE CASCADE ON DELETE RESTRICT;",
            ]
        )""",
    """                f'  REFERENCES "app"."{target_table}" ("tenant_id", "{relation.target_field}")',
                "  ON UPDATE CASCADE ON DELETE RESTRICT;",
            ]
        )
        if relation.enforces_uniqueness:
            # This is the whole difference between one-to-one and many-to-one:
            # the same foreign key, forbidden to repeat. Scoped by tenant_id,
            # like every other constraint in this schema.
            unique = f"uq_{relation.source}_{relation.source_field}"
            blocks.extend(
                [
                    f'ALTER TABLE "app"."{source_table}" DROP CONSTRAINT IF EXISTS "{unique}";',
                    f'ALTER TABLE "app"."{source_table}" ADD CONSTRAINT "{unique}"',
                    f'  UNIQUE ("tenant_id", "{relation.source_field}");',
                ]
            )""",
)

patch(
    f"{PS}/java_production_target.py",
    """        (relation.source, relation.source_field)
        for relation in request.relations
        if relation.source_field is not None and relation.target_field == "id\"""",
    """        (relation.source, relation.source_field)
        for relation in request.canonical_relations
        if relation.source_field is not None and relation.target_field == "id\"""",
)

patch(
    f"{PS}/java_production_target.py",
    """        (relation.source_field, relation.target)
        for relation in request.relations
        if relation.source == entity_name
        and relation.source_field is not None
        and relation.target_field == "id\"""",
    """        (relation.source_field, relation.target)
        for relation in request.canonical_relations
        if relation.source == entity_name
        and relation.source_field is not None
        and relation.target_field == "id\"""",
)

patch(
    f"{PS}/python_production_target.py",
    """        relation.source == entity and relation.source_field == field.name and relation.target_field == "id"
        for relation in request.relations""",
    """        relation.source == entity and relation.source_field == field.name and relation.target_field == "id"
        for relation in request.canonical_relations""",
)

print("FIX 6 generation sites applied")
