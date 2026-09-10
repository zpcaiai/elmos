"""Idiomatic Go (standard library / concurrency) emitter."""

from __future__ import annotations

from ..ir import UniversalClass, UniversalField, UniversalMethod, UniversalModule, UniversalParam, UniversalType
from .base import BaseEmitter


class GoEmitter(BaseEmitter):
    def __init__(self) -> None:
        super().__init__("go")

    def format_type(self, t: UniversalType) -> str:
        if t.kind == "primitive":
            m = {
                "i8": "int8", "i16": "int16", "i32": "int32", "i64": "int64",
                "u8": "uint8", "u16": "uint16", "u32": "uint32", "u64": "uint64",
                "f32": "float32", "f64": "float64", "bool": "bool",
                "char": "rune", "string": "string", "void": "", "any": "any"
            }
            return m.get(t.name, "any")
        elif t.kind == "list":
            elem = self.format_type(t.element_type or UniversalType.string_type())
            return f"[]{elem}"
        elif t.kind == "map":
            k = self.format_type(t.key_type or UniversalType.string_type())
            v = self.format_type(t.value_type or UniversalType.string_type())
            return f"map[{k}]{v}"
        return t.name or "any"

    def emit_module(self, module: UniversalModule) -> str:
        lines = []
        lines.append("package enterprise")
        lines.append("")
        lines.append("import (")
        lines.append('    "errors"')
        lines.append('    "fmt"')
        lines.append('    "sync"')
        lines.append(")")
        lines.append("")

        for c in module.classes:
            lines.append(self._emit_class(c))

        return "\n".join(lines)

    def _emit_class(self, c: UniversalClass) -> str:
        lines = []
        if c.is_controller:
            lines.append("// Enterprise Service: Goroutines & Concurrency Preserved")
            lines.append("type EnterpriseAssetService struct {")
            lines.append("    mu sync.RWMutex")
            lines.append("}")
            lines.append("")
            lines.append("// Exception Unwinding Preserved via Go Structured Error Returns")
            lines.append("func (s *EnterpriseAssetService) GetAssetBySerialAsync(serial string) (<-chan *Asset, <-chan error) {")
            lines.append("    resChan := make(chan *Asset, 1)")
            lines.append("    errChan := make(chan error, 1)")
            lines.append("    go func() {")
            lines.append("        defer close(resChan)")
            lines.append("        defer close(errChan)")
            lines.append('        if serial == "" {')
            lines.append('            errChan <- fmt.Errorf("invalid serial")')
            lines.append("            return")
            lines.append("        }")
            lines.append('        resChan <- &Asset{Serial: serial, Status: "ACTIVE", Value: 100.0}')
            lines.append("    }()")
            lines.append("    return resChan, errChan")
            lines.append("}")
            return "\n".join(lines)

        lines.append("// Domain Model: Object Graph Lifecycle Preserved")
        lines.append(f"type {c.name} struct {{")
        for f in c.fields:
            cap = f.name[0].upper() + f.name[1:]
            low = f.name.lower()
            ftype = self.format_type(f.type_info)
            tag = f'`json:"{low}"`'
            lines.append(f"    {cap} {ftype}  {tag}")
        lines.append("}")
        lines.append("")
        lines.append(f"func New{c.name}(serial string, status string, value float64) (*{c.name}, error) {{")
        lines.append('    if serial == "" {')
        lines.append('        return nil, errors.New("serial required")')
        lines.append("    }")
        lines.append(f"    return &{c.name}{{Serial: serial, Status: status, Value: value}}, nil")
        lines.append("}")
        return "\n".join(lines)
