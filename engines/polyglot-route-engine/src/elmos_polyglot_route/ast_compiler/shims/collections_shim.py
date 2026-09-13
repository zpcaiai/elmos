"""Cross-language collections standard library shim across 11 enterprise languages."""

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
        'cpp': 'std::vector<{T}>',
        'swift': '[{T}]',
        'objc': 'NSMutableArray<{T}*>*',
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
        'cpp': 'std::unordered_map<{K}, {V}>',
        'swift': '[{K}: {V}]',
        'objc': 'NSMutableDictionary<{K}*, {V}*>*',
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
        'cpp': 'std::unordered_set<{T}>',
        'swift': 'Set<{T}>',
        'objc': 'NSMutableSet<{T}*>*',
    },
}

def get_collection_type(collection_kind: str, target_lang: str, elem_type: str = 'string', val_type: str = 'string') -> str:
    lang = target_lang.lower().strip()
    pattern = COLLECTIONS_MAP.get(collection_kind, {}).get(lang, '{T}[]')
    return pattern.replace('{T}', elem_type).replace('{K}', elem_type).replace('{V}', val_type)

def list_add(list_expr: str, item_expr: str, lang: str) -> str:
    l = lang.lower().strip()
    if l in ('java', 'kotlin'):
        return f"{list_expr}.add({item_expr})"
    elif l in ('csharp', 'cs'):
        return f"{list_expr}.Add({item_expr})"
    elif l in ('python', 'py'):
        return f"{list_expr}.append({item_expr})"
    elif l in ('typescript', 'ts', 'javascript', 'js'):
        return f"{list_expr}.push({item_expr})"
    elif l in ('go', 'golang'):
        return f"{list_expr} = append({list_expr}, {item_expr})"
    elif l in ('rust', 'rs'):
        return f"{list_expr}.push({item_expr})"
    elif l == 'php':
        return f"{list_expr}[] = {item_expr}"
    elif l in ('cpp', 'c++'):
        return f"{list_expr}.push_back({item_expr})"
    elif l == 'swift':
        return f"{list_expr}.append({item_expr})"
    elif l in ('objc', 'objective-c'):
        return f"[{list_expr} addObject:{item_expr}]"
    return f"{list_expr}.append({item_expr})"

def list_size(list_expr: str, lang: str) -> str:
    l = lang.lower().strip()
    if l in ('java', 'kotlin'):
        return f"{list_expr}.size()"
    elif l in ('csharp', 'cs'):
        return f"{list_expr}.Count"
    elif l in ('python', 'py', 'go', 'golang'):
        return f"len({list_expr})"
    elif l in ('typescript', 'ts', 'javascript', 'js'):
        return f"{list_expr}.length"
    elif l in ('rust', 'rs'):
        return f"{list_expr}.len()"
    elif l == 'php':
        return f"count({list_expr})"
    elif l in ('cpp', 'c++'):
        return f"{list_expr}.size()"
    elif l == 'swift':
        return f"{list_expr}.count"
    elif l in ('objc', 'objective-c'):
        return f"[{list_expr} count]"
    return f"len({list_expr})"

def list_contains(list_expr: str, item_expr: str, lang: str) -> str:
    l = lang.lower().strip()
    if l in ('java', 'kotlin'):
        return f"{list_expr}.contains({item_expr})"
    elif l in ('csharp', 'cs'):
        return f"{list_expr}.Contains({item_expr})"
    elif l in ('python', 'py'):
        return f"({item_expr} in {list_expr})"
    elif l in ('typescript', 'ts', 'javascript', 'js'):
        return f"{list_expr}.includes({item_expr})"
    elif l in ('rust', 'rs'):
        return f"{list_expr}.contains(&{item_expr})"
    elif l == 'php':
        return f"in_array({item_expr}, {list_expr}, true)"
    elif l in ('cpp', 'c++'):
        return f"(std::find({list_expr}.begin(), {list_expr}.end(), {item_expr}) != {list_expr}.end())"
    elif l == 'swift':
        return f"{list_expr}.contains({item_expr})"
    elif l in ('objc', 'objective-c'):
        return f"[{list_expr} containsObject:{item_expr}]"
    return f"({item_expr} in {list_expr})"

def list_clear(list_expr: str, lang: str) -> str:
    l = lang.lower().strip()
    if l in ('java', 'kotlin', 'csharp', 'cs', 'cpp', 'c++'):
        return f"{list_expr}.clear()" if l != 'csharp' else f"{list_expr}.Clear()"
    elif l in ('python', 'py'):
        return f"{list_expr}.clear()"
    elif l in ('typescript', 'ts', 'javascript', 'js'):
        return f"{list_expr}.length = 0"
    elif l in ('rust', 'rs'):
        return f"{list_expr}.clear()"
    elif l in ('go', 'golang'):
        return f"{list_expr} = {list_expr}[:0]"
    elif l == 'php':
        return f"{list_expr} = []"
    elif l == 'swift':
        return f"{list_expr}.removeAll()"
    elif l in ('objc', 'objective-c'):
        return f"[{list_expr} removeAllObjects]"
    return f"{list_expr}.clear()"

def map_get(map_expr: str, key_expr: str, lang: str) -> str:
    l = lang.lower().strip()
    if l in ('java', 'kotlin'):
        return f"{map_expr}.get({key_expr})"
    elif l in ('rust', 'rs'):
        return f"{map_expr}.get(&{key_expr})"
    elif l in ('objc', 'objective-c'):
        return f"[{map_expr} objectForKey:{key_expr}]"
    return f"{map_expr}[{key_expr}]"

def map_put(map_expr: str, key_expr: str, val_expr: str, lang: str) -> str:
    l = lang.lower().strip()
    if l in ('java', 'kotlin'):
        return f"{map_expr}.put({key_expr}, {val_expr})"
    elif l in ('rust', 'rs'):
        return f"{map_expr}.insert({key_expr}, {val_expr})"
    elif l in ('typescript', 'ts') and 'new Map' in map_expr:
        return f"{map_expr}.set({key_expr}, {val_expr})"
    elif l in ('objc', 'objective-c'):
        return f"[{map_expr} setObject:{val_expr} forKey:{key_expr}]"
    return f"{map_expr}[{key_expr}] = {val_expr}"

def map_contains_key(map_expr: str, key_expr: str, lang: str) -> str:
    l = lang.lower().strip()
    if l in ('java', 'kotlin'):
        return f"{map_expr}.containsKey({key_expr})"
    elif l in ('csharp', 'cs'):
        return f"{map_expr}.ContainsKey({key_expr})"
    elif l in ('python', 'py'):
        return f"({key_expr} in {map_expr})"
    elif l in ('typescript', 'ts', 'javascript', 'js'):
        return f"{map_expr}.has({key_expr})"
    elif l in ('rust', 'rs'):
        return f"{map_expr}.contains_key(&{key_expr})"
    elif l == 'php':
        return f"array_key_exists({key_expr}, {map_expr})"
    elif l in ('cpp', 'c++'):
        return f"({map_expr}.find({key_expr}) != {map_expr}.end())"
    elif l == 'swift':
        return f"({map_expr}[{key_expr}] != nil)"
    elif l in ('objc', 'objective-c'):
        return f"([{map_expr} objectForKey:{key_expr}] != nil)"
    return f"({key_expr} in {map_expr})"

def map_remove(map_expr: str, key_expr: str, lang: str) -> str:
    l = lang.lower().strip()
    if l in ('java', 'kotlin'):
        return f"{map_expr}.remove({key_expr})"
    elif l in ('csharp', 'cs'):
        return f"{map_expr}.Remove({key_expr})"
    elif l in ('python', 'py'):
        return f"{map_expr}.pop({key_expr}, None)"
    elif l in ('typescript', 'ts', 'javascript', 'js'):
        return f"{map_expr}.delete({key_expr})"
    elif l in ('go', 'golang'):
        return f"delete({map_expr}, {key_expr})"
    elif l in ('rust', 'rs'):
        return f"{map_expr}.remove(&{key_expr})"
    elif l == 'php':
        return f"unset({map_expr}[{key_expr}])"
    elif l in ('cpp', 'c++'):
        return f"{map_expr}.erase({key_expr})"
    elif l == 'swift':
        return f"{map_expr}.removeValue(forKey: {key_expr})"
    elif l in ('objc', 'objective-c'):
        return f"[{map_expr} removeObjectForKey:{key_expr}]"
    return f"{map_expr}.remove({key_expr})"

def set_add(set_expr: str, item_expr: str, lang: str) -> str:
    l = lang.lower().strip()
    if l in ('java', 'kotlin'):
        return f"{set_expr}.add({item_expr})"
    elif l in ('csharp', 'cs'):
        return f"{set_expr}.Add({item_expr})"
    elif l in ('python', 'py'):
        return f"{set_expr}.add({item_expr})"
    elif l in ('typescript', 'ts', 'javascript', 'js'):
        return f"{set_expr}.add({item_expr})"
    elif l in ('go', 'golang'):
        return f"{set_expr}[{item_expr}] = struct{{}}{{}}"
    elif l in ('rust', 'rs'):
        return f"{set_expr}.insert({item_expr})"
    elif l in ('cpp', 'c++'):
        return f"{set_expr}.insert({item_expr})"
    elif l == 'swift':
        return f"{set_expr}.insert({item_expr})"
    elif l in ('objc', 'objective-c'):
        return f"[{set_expr} addObject:{item_expr}]"
    return f"{set_expr}.add({item_expr})"

def set_contains(set_expr: str, item_expr: str, lang: str) -> str:
    l = lang.lower().strip()
    if l in ('java', 'kotlin'):
        return f"{set_expr}.contains({item_expr})"
    elif l in ('csharp', 'cs'):
        return f"{set_expr}.Contains({item_expr})"
    elif l in ('python', 'py'):
        return f"({item_expr} in {set_expr})"
    elif l in ('typescript', 'ts', 'javascript', 'js'):
        return f"{set_expr}.has({item_expr})"
    elif l in ('rust', 'rs'):
        return f"{set_expr}.contains(&{item_expr})"
    elif l in ('cpp', 'c++'):
        return f"({set_expr}.find({item_expr}) != {set_expr}.end())"
    elif l == 'swift':
        return f"{set_expr}.contains({item_expr})"
    elif l in ('objc', 'objective-c'):
        return f"[{set_expr} containsObject:{item_expr}]"
    return f"({item_expr} in {set_expr})"
