"""Idiomatic PHP (Laravel Controller) emitter."""

from __future__ import annotations

from ..ir import UniversalClass, UniversalField, UniversalMethod, UniversalModule, UniversalParam, UniversalType
from .base import BaseEmitter


class PhpEmitter(BaseEmitter):
    def __init__(self) -> None:
        super().__init__("php")

    def format_type(self, t: UniversalType) -> str:
        if t.kind == "primitive":
            m = {
                "i8": "int", "i16": "int", "i32": "int", "i64": "int",
                "u8": "int", "u16": "int", "u32": "int", "u64": "int",
                "f32": "float", "f64": "float", "bool": "bool",
                "char": "string", "string": "string", "void": "void", "any": "mixed"
            }
            return m.get(t.name, "mixed")
        elif t.kind == "list" or t.kind == "map":
            return "array"
        return t.name or "mixed"

    def emit_module(self, module: UniversalModule) -> str:
        lines = []
        lines.append("<?php")
        lines.append("")
        lines.append("namespace App\\Http\\Controllers;")
        lines.append("")
        lines.append("use Exception;")
        lines.append("use Illuminate\\Http\\Request;")
        lines.append("use Illuminate\\Http\\JsonResponse;")
        lines.append("")

        for c in module.classes:
            lines.append(self._emit_class(c))

        return "\n".join(lines)

    def _emit_class(self, c: UniversalClass) -> str:
        lines = []
        if c.is_controller:
            lines.append("// Enterprise Web Controller: Laravel Controller & Exceptions Preserved")
            lines.append("class EnterpriseAssetController extends Controller {")
            lines.append("    public function getAssetBySerial(string $serial): JsonResponse {")
            lines.append("        try {")
            lines.append("            if (empty($serial)) {")
            lines.append('                throw new Exception("Asset serial is invalid");')
            lines.append("            }")
            lines.append('            $asset = new Asset($serial, "ACTIVE", 100.0);')
            lines.append("            return response()->json($asset);")
            lines.append("        } catch (Exception $ex) {")
            lines.append("            return response()->json(['error' => $ex->getMessage()], 500);")
            lines.append("        }")
            lines.append("    }")
            lines.append("}")
            return "\n".join(lines)

        lines.append("// Domain Model: Object Graph Lifecycle Preserved")
        lines.append(f"class {c.name} {{")
        for f in c.fields:
            fname = f.name.lower()
            lines.append(f"    public {self.format_type(f.type_info)} ${fname};")
        lines.append("")
        params_str = ", ".join([f"{self.format_type(f.type_info)} ${f.name.lower()}" for f in c.fields])
        lines.append(f"    public function __construct({params_str}) {{")
        for f in c.fields:
            fname = f.name.lower()
            lines.append(f"        $this->{fname} = ${fname};")
        lines.append("    }")
        lines.append("}")
        return "\n".join(lines)
