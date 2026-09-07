from __future__ import annotations
import json, sys
from pathlib import Path
import jsonschema

def validate_graph(path: Path, schema_path: Path, groups: tuple[str, ...], ref_fields: tuple[str, ...], source_map_key: str = 'source_map') -> list[str]:
    errors: list[str] = []
    data = json.loads(path.read_text())
    schema = json.loads(schema_path.read_text())
    try:
        jsonschema.validate(data, schema)
    except Exception as exc:
        return [str(exc)]
    ids: set[str] = set()
    all_nodes: list[dict] = []
    for group in groups:
        values = data.get(group, [])
        for node in values:
            if not isinstance(node, dict) or 'id' not in node:
                continue
            if node['id'] in ids:
                errors.append(f'duplicate id: {node["id"]}')
            ids.add(node['id']); all_nodes.append(node)
    for node in all_nodes:
        refs: list[str] = []
        for field in ref_fields:
            refs.extend(node.get(field, []) or [])
        for ref in refs:
            if ref not in ids:
                errors.append(f'{node["id"]}: unknown reference {ref}')
    mapped = {entry.get('node_id') for entry in data.get(source_map_key, []) if isinstance(entry, dict)}
    for node in all_nodes:
        if node['id'] not in mapped:
            errors.append(f'{node["id"]}: missing source map')
    return errors
