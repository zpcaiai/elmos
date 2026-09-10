"""Cross-language string manipulation standard library shim."""

from __future__ import annotations

def string_length(var_name: str, lang: str) -> str:
    lang = lang.lower()
    if lang in ('java', 'kotlin'):
        return f"{var_name}.length()"
    elif lang in ('csharp',):
        return f"{var_name}.Length"
    elif lang in ('python',):
        return f"len({var_name})"
    elif lang in ('typescript',):
        return f"{var_name}.length"
    elif lang in ('go',):
        return f"len({var_name})"
    elif lang in ('rust',):
        return f"{var_name}.len()"
    elif lang in ('php',):
        return f"strlen({var_name})"
    return f"len({var_name})"

def string_trim(var_name: str, lang: str) -> str:
    lang = lang.lower()
    if lang in ('java', 'kotlin'):
        return f"{var_name}.trim()"
    elif lang in ('csharp',):
        return f"{var_name}.Trim()"
    elif lang in ('python',):
        return f"{var_name}.strip()"
    elif lang in ('typescript',):
        return f"{var_name}.trim()"
    elif lang in ('go',):
        return f"strings.TrimSpace({var_name})"
    elif lang in ('rust',):
        return f"{var_name}.trim().to_string()"
    elif lang in ('php',):
        return f"trim({var_name})"
    return f"{var_name}.trim()"
