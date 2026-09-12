from __future__ import annotations

from typing import Any
from elmos_uir_java_typescript.ts_types import JavaToTsTypeMapper

class TsLowerer:
    def __init__(self):
        self.type_mapper = JavaToTsTypeMapper()

    def lower_module(self, module: Any) -> str:
        lines = []
        types = getattr(module, "types", [])
        for t in types:
            lines.append(self.lower_type_decl(t))
        return "\n\n".join(lines)
        
    def lower_type_decl(self, type_decl: Any) -> str:
        kind = getattr(type_decl, "kind", "class")
        name = getattr(type_decl, "name", "Unknown")
        modifiers = getattr(type_decl, "modifiers", [])
        
        is_export = "public" in modifiers
        export_prefix = "export " if is_export else ""
        
        if kind == "class":
            return self.lower_class(type_decl, export_prefix)
        elif kind == "interface":
            return self.lower_interface(type_decl, export_prefix)
        elif kind == "enum":
            return self.lower_enum(type_decl, export_prefix)
        else:
            return f"{export_prefix}class {name} {{ /* unsupported kind {kind} */ }}"

    def lower_class(self, type_decl: Any, export_prefix: str) -> str:
        name = getattr(type_decl, "name", "Unknown")
        modifiers = getattr(type_decl, "modifiers", [])
        fields = getattr(type_decl, "fields", [])
        methods = getattr(type_decl, "methods", [])
        
        lines = []
        lines.append(f"{export_prefix}class {name} {{")
        
        for f in fields:
            f_name = getattr(f, "name", "")
            f_type = self.type_mapper.map_type(getattr(f, "type", None))
            f_mods = getattr(f, "modifiers", [])
            
            ts_mods = []
            if "private" in f_mods: ts_mods.append("private")
            if "protected" in f_mods: ts_mods.append("protected")
            if "public" in f_mods: ts_mods.append("public")
            if "static" in f_mods: ts_mods.append("static")
            if "final" in f_mods: ts_mods.append("readonly")
            
            mod_str = " ".join(ts_mods) + " " if ts_mods else ""
            lines.append(f"  {mod_str}{f_name}: {f_type};")
            
        for m in methods:
            m_name = getattr(m, "name", "")
            is_constructor = getattr(m, "is_constructor", False)
            if is_constructor:
                m_name = "constructor"
                
            m_mods = getattr(m, "modifiers", [])
            ts_mods = []
            if not is_constructor:
                if "private" in m_mods: ts_mods.append("private")
                if "protected" in m_mods: ts_mods.append("protected")
                if "public" in m_mods: ts_mods.append("public")
                if "static" in m_mods: ts_mods.append("static")
                
            mod_str = " ".join(ts_mods) + " " if ts_mods else ""
            
            params = getattr(m, "params", [])
            param_strs = []
            for p in params:
                p_name = getattr(p, "name", "")
                p_type = self.type_mapper.map_type(getattr(p, "type", None))
                param_strs.append(f"{p_name}: {p_type}")
                
            ret_type_str = ""
            if not is_constructor:
                ret_type = self.type_mapper.map_type(getattr(m, "return_type", None))
                ret_type_str = f": {ret_type}"
                
            lines.append(f"  {mod_str}{m_name}({', '.join(param_strs)}){ret_type_str} {{")
            lines.append("    // TODO: implement body")
            lines.append("  }")
            
        lines.append("}")
        return "\n".join(lines)

    def lower_interface(self, type_decl: Any, export_prefix: str) -> str:
        name = getattr(type_decl, "name", "Unknown")
        methods = getattr(type_decl, "methods", [])
        
        lines = []
        lines.append(f"{export_prefix}interface {name} {{")
        
        for m in methods:
            m_name = getattr(m, "name", "")
            params = getattr(m, "params", [])
            param_strs = []
            for p in params:
                p_name = getattr(p, "name", "")
                p_type = self.type_mapper.map_type(getattr(p, "type", None))
                param_strs.append(f"{p_name}: {p_type}")
                
            ret_type = self.type_mapper.map_type(getattr(m, "return_type", None))
            lines.append(f"  {m_name}({', '.join(param_strs)}): {ret_type};")
            
        lines.append("}")
        return "\n".join(lines)

    def lower_enum(self, type_decl: Any, export_prefix: str) -> str:
        name = getattr(type_decl, "name", "Unknown")
        constants = getattr(type_decl, "enum_constants", [])
        
        lines = []
        lines.append(f"{export_prefix}enum {name} {{")
        for c in constants:
            lines.append(f"  {c} = \"{c}\",")
        lines.append("}")
        return "\n".join(lines)
