"""I/O and Logging standard library shim across 8 languages."""

from __future__ import annotations


def log_info(lang: str, msg_expr: str) -> str:
    lang = lang.lower()
    if lang in ("csharp", "cs"):
        return f"Console.WriteLine({msg_expr});"
    elif lang == "java":
        return f"System.out.println({msg_expr});"
    elif lang in ("python", "py"):
        return f"print({msg_expr})"
    elif lang in ("typescript", "ts"):
        return f"console.log({msg_expr});"
    elif lang in ("go", "golang"):
        return f"fmt.Println({msg_expr})"
    elif lang in ("rust", "rs"):
        return f"println!(\"{{}}\", {msg_expr});"
    elif lang in ("kotlin", "kt"):
        return f"println({msg_expr})"
    elif lang == "php":
        return f"echo {msg_expr} . PHP_EOL;"
    return f"print({msg_expr})"
