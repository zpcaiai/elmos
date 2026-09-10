"""Cross-language collections standard library shim."""

from __future__ import annotations

COLLECTIONS_MAP: dict[str, dict[str, str]] = {
    'list_type': {
        'java': 'java.util.List<{T}>',
        'csharp': 'System.Collections.Generic.List<{T}>',
        'python': 'list[{T}]',
        'typescript': '{T}[]',
        'go': '[]{T}',
        'rust': 'Vec<{T}>',
        'kotlin': 'List<{T}>',
        'php': 'array',
    },
    'map_type': {
        'java': 'java.util.Map<{K}, {V}>',
        'csharp': 'System.Collections.Generic.Dictionary<{K}, {V}>',
        'python': 'dict[{K}, {V}]',
        'typescript': 'Map<{K}, {V}>',
        'go': 'map[{K}]{V}',
        'rust': 'std::collections::HashMap<{K}, {V}>',
        'kotlin': 'Map<{K}, {V}>',
        'php': 'array',
    },
    'set_type': {
        'java': 'java.util.Set<{T}>',
        'csharp': 'System.Collections.Generic.HashSet<{T}>',
        'python': 'set[{T}]',
        'typescript': 'Set<{T}>',
        'go': 'map[{T}]struct{}',
        'rust': 'std::collections::HashSet<{T}>',
        'kotlin': 'Set<{T}>',
        'php': 'array',
    },
}

def get_collection_type(collection_kind: str, target_lang: str, elem_type: str = 'string', val_type: str = 'string') -> str:
    pattern = COLLECTIONS_MAP.get(collection_kind, {}).get(target_lang.lower(), '{T}[]')
    return pattern.replace('{T}', elem_type).replace('{K}', elem_type).replace('{V}', val_type)
