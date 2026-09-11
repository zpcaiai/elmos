"""System I/O lowering for the industrial file/stdio subset."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from elmos_polyglot_route.ast_compiler.ir import IoReadStmt, IoWriteStmt, UniversalModule
from elmos_polyglot_route.industrial.concurrency import normalize_language

IO_PRIMITIVES: dict[str, dict[str, str]] = {
    "java": {"read": "Files.readString", "write": "Files.writeString", "stdio": "System.out"},
    "csharp": {"read": "File.ReadAllText", "write": "File.WriteAllText", "stdio": "Console"},
    "python": {"read": "Path.read_text", "write": "Path.write_text", "stdio": "print"},
    "typescript": {"read": "fs.readFileSync", "write": "fs.writeFileSync", "stdio": "console"},
    "go": {"read": "os.ReadFile", "write": "os.WriteFile", "stdio": "fmt"},
    "rust": {"read": "fs::read_to_string", "write": "fs::write", "stdio": "println"},
    "kotlin": {"read": "Files.readString", "write": "Files.writeString", "stdio": "println"},
    "php": {"read": "file_get_contents", "write": "file_put_contents", "stdio": "echo"},
    "cpp": {"read": "std::ifstream", "write": "std::ofstream", "stdio": "std::cout"},
    "objc": {"read": "stringWithContentsOfFile", "write": "writeToFile", "stdio": "NSLog"},
    "swift": {"read": "String(contentsOfFile:)", "write": "write(toFile:)", "stdio": "print"},
    "react": {"read": "fs.readFileSync", "write": "fs.writeFileSync", "stdio": "console"},
    "flutter": {"read": "File.readAsStringSync", "write": "File.writeAsStringSync", "stdio": "print"},
    "vb6": {"read": "Input #", "write": "Print #", "stdio": "Debug.Print"},
    "vcpp6": {"read": "CStdioFile.ReadString", "write": "CStdioFile.WriteString", "stdio": "printf"},
}


def io_runtime(language: str) -> dict[str, str]:
    key = normalize_language(language)
    if key not in IO_PRIMITIVES:
        raise ValueError(f"No industrial I/O mapping for {language}")
    return IO_PRIMITIVES[key]


class SystemIoEngine:
    @classmethod
    def lower_module(cls, module: UniversalModule, target_language: str) -> UniversalModule:
        target = normalize_language(target_language)
        out = deepcopy(module)
        out.metadata = dict(out.metadata)
        out.metadata["io_runtime"] = io_runtime(target)
        return out

    @classmethod
    def collect_constructs(cls, stmts: list[Any]) -> set[str]:
        found: set[str] = set()
        stack = list(stmts)
        while stack:
            stmt = stack.pop()
            if isinstance(stmt, IoReadStmt):
                found.add("io-read")
            elif isinstance(stmt, IoWriteStmt):
                found.add("io-write")
            for attr in ("body", "then_body", "else_body", "try_body", "finally_body"):
                inner = getattr(stmt, attr, None)
                if isinstance(inner, list):
                    stack.extend(inner)
        return found
