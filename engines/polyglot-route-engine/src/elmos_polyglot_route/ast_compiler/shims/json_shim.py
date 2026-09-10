"""Cross-language JSON serialization/deserialization shim."""

from __future__ import annotations

def json_serialize(obj_expr: str, lang: str) -> str:
    lang = lang.lower()
    if lang in ('java',):
        return f"objectMapper.writeValueAsString({obj_expr})"
    elif lang in ('csharp',):
        return f"System.Text.Json.JsonSerializer.Serialize({obj_expr})"
    elif lang in ('python',):
        return f"json.dumps({obj_expr})"
    elif lang in ('typescript',):
        return f"JSON.stringify({obj_expr})"
    elif lang in ('go',):
        return f"json.Marshal({obj_expr})"
    elif lang in ('rust',):
        return f"serde_json::to_string(&{obj_expr})"
    elif lang in ('kotlin',):
        return f"Json.encodeToString({obj_expr})"
    elif lang in ('php',):
        return f"json_encode({obj_expr})"
    return f"json.dumps({obj_expr})"
