"""Cross-language math & arithmetic standard library shim."""

from __future__ import annotations

def math_abs(expr: str, lang: str) -> str:
    lang = lang.lower()
    if lang in ('java', 'kotlin'):
        return f"Math.abs({expr})"
    elif lang in ('csharp',):
        return f"Math.Abs({expr})"
    elif lang in ('python',):
        return f"abs({expr})"
    elif lang in ('typescript',):
        return f"Math.abs({expr})"
    elif lang in ('go',):
        return f"math.Abs(float64({expr}))"
    elif lang in ('rust',):
        return f"({expr}).abs()"
    elif lang in ('php',):
        return f"abs({expr})"
    return f"abs({expr})"
