"""Cross-language JSON serialization/deserialization shim across 11 enterprise languages."""

from __future__ import annotations

def json_serialize(obj_expr: str, lang: str) -> str:
    l = lang.lower().strip()
    if l == 'java':
        return f"objectMapper.writeValueAsString({obj_expr})"
    elif l in ('csharp', 'cs'):
        return f"System.Text.Json.JsonSerializer.Serialize({obj_expr})"
    elif l in ('python', 'py'):
        return f"json.dumps({obj_expr})"
    elif l in ('typescript', 'ts', 'javascript', 'js'):
        return f"JSON.stringify({obj_expr})"
    elif l in ('go', 'golang'):
        return f"json.Marshal({obj_expr})"
    elif l in ('rust', 'rs'):
        return f"serde_json::to_string(&{obj_expr})"
    elif l in ('kotlin', 'kt'):
        return f"Json.encodeToString({obj_expr})"
    elif l == 'php':
        return f"json_encode({obj_expr})"
    elif l in ('cpp', 'c++'):
        return f"nlohmann::json({obj_expr}).dump()"
    elif l == 'swift':
        return f"String(data: try JSONEncoder().encode({obj_expr}), encoding: .utf8)!"
    elif l in ('objc', 'objective-c'):
        return f"[[NSString alloc] initWithData:[NSJSONSerialization dataWithJSONObject:{obj_expr} options:0 error:nil] encoding:NSUTF8StringEncoding]"
    return f"json.dumps({obj_expr})"

def json_deserialize(json_expr: str, type_name: str, lang: str) -> str:
    l = lang.lower().strip()
    if l == 'java':
        return f"objectMapper.readValue({json_expr}, {type_name}.class)"
    elif l in ('csharp', 'cs'):
        return f"System.Text.Json.JsonSerializer.Deserialize<{type_name}>({json_expr})"
    elif l in ('python', 'py'):
        return f"json.loads({json_expr})"
    elif l in ('typescript', 'ts', 'javascript', 'js'):
        return f"JSON.parse({json_expr}) as {type_name}"
    elif l in ('go', 'golang'):
        return f"json.Unmarshal([]byte({json_expr}), &{type_name.lower()})"
    elif l in ('rust', 'rs'):
        return f"serde_json::from_str::<{type_name}>({json_expr})"
    elif l in ('kotlin', 'kt'):
        return f"Json.decodeFromString<{type_name}>({json_expr})"
    elif l == 'php':
        return f"json_decode({json_expr}, true)"
    elif l in ('cpp', 'c++'):
        return f"nlohmann::json::parse({json_expr}).get<{type_name}>()"
    elif l == 'swift':
        return f"try JSONDecoder().decode({type_name}.self, from: {json_expr}.data(using: .utf8)!)"
    elif l in ('objc', 'objective-c'):
        return f"[NSJSONSerialization JSONObjectWithData:[{json_expr} dataUsingEncoding:NSUTF8StringEncoding] options:0 error:nil]"
    return f"json.loads({json_expr})"

