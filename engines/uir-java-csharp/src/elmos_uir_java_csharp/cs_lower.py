from __future__ import annotations
from typing import Any
from elmos_uir_java_csharp.cs_types import JavaToCsTypeMapper

class CsLowerer:
    def __init__(self):
        self.type_mapper = JavaToCsTypeMapper()

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
        
        cs_mods = []
        if "public" in modifiers: cs_mods.append("public")
        elif "private" in modifiers: cs_mods.append("private")
        elif "protected" in modifiers: cs_mods.append("protected")
        else: cs_mods.append("internal")
        
        if "final" in modifiers and kind == "class":
            cs_mods.append("sealed")
            
        mod_str = " ".join(cs_mods) + " " if cs_mods else ""
        
        if kind == "class":
            return self.lower_class(type_decl, mod_str)
        elif kind == "interface":
            # Convention: Ensure I prefix
            if not name.startswith("I"): name = f"I{name}"
            return self.lower_interface(type_decl, mod_str, name)
        elif kind == "enum":
            return self.lower_enum(type_decl, mod_str)
        else:
            return f"{mod_str}class {name} {{ /* unsupported kind */ }}"

    def lower_class(self, type_decl: Any, mod_str: str) -> str:
        name = getattr(type_decl, "name", "Unknown")
        fields = getattr(type_decl, "fields", [])
        methods = getattr(type_decl, "methods", [])
        
        bases = []
        superclass = getattr(type_decl, "superclass", None)
        if superclass: bases.append(self.type_mapper.map_type(superclass))
        
        interfaces = getattr(type_decl, "interfaces", [])
        for i in interfaces: bases.append(self.type_mapper.map_type(i))
            
        base_str = f" : {', '.join(bases)}" if bases else ""
        
        lines = [f"{mod_str}class {name}{base_str}", "{"]
        
        for f in fields:
            f_name = getattr(f, "name", "")
            f_type = self.type_mapper.map_type(getattr(f, "type", None))
            f_mods = getattr(f, "modifiers", [])
            
            ts_mods = []
            if "public" in f_mods: ts_mods.append("public")
            elif "private" in f_mods: ts_mods.append("private")
            else: ts_mods.append("private") # Default field visibility
            
            if "static" in f_mods: ts_mods.append("static")
            if "final" in f_mods: ts_mods.append("readonly")
            
            fm_str = " ".join(ts_mods) + " "
            lines.append(f"    {fm_str}{f_type} {f_name};")
            
        for m in methods:
            m_name = getattr(m, "name", "")
            # Pascal case convention
            if m_name and m_name[0].islower():
                m_name = m_name[0].upper() + m_name[1:]
                
            is_constructor = getattr(m, "is_constructor", False)
            if is_constructor:
                m_name = name
                
            m_mods = getattr(m, "modifiers", [])
            ts_mods = []
            if "public" in m_mods: ts_mods.append("public")
            elif "private" in m_mods: ts_mods.append("private")
            elif "protected" in m_mods: ts_mods.append("protected")
            else: ts_mods.append("internal")
                
            if "static" in m_mods and not is_constructor: ts_mods.append("static")
            if "@Override" in m_mods: ts_mods.append("override")
            
            fm_str = " ".join(ts_mods) + " "
            
            params = getattr(m, "params", [])
            param_strs = []
            for p in params:
                p_name = getattr(p, "name", "")
                p_type = self.type_mapper.map_type(getattr(p, "type", None))
                param_strs.append(f"{p_type} {p_name}")
                
            ret_type_str = ""
            if not is_constructor:
                ret_type = self.type_mapper.map_type(getattr(m, "return_type", None))
                ret_type_str = f"{ret_type} "
                
            lines.append(f"    {fm_str}{ret_type_str}{m_name}({', '.join(param_strs)})")
            lines.append("    {")
            lines.append("        // TODO")
            lines.append("    }")
            
        lines.append("}")
        return "\n".join(lines)

    def lower_interface(self, type_decl: Any, mod_str: str, name: str) -> str:
        methods = getattr(type_decl, "methods", [])
        
        lines = [f"{mod_str}interface {name}", "{"]
        for m in methods:
            m_name = getattr(m, "name", "")
            if m_name and m_name[0].islower(): m_name = m_name[0].upper() + m_name[1:]
            
            params = getattr(m, "params", [])
            param_strs = []
            for p in params:
                p_name = getattr(p, "name", "")
                p_type = self.type_mapper.map_type(getattr(p, "type", None))
                param_strs.append(f"{p_type} {p_name}")
                
            ret_type = self.type_mapper.map_type(getattr(m, "return_type", None))
            lines.append(f"    {ret_type} {m_name}({', '.join(param_strs)});")
            
        lines.append("}")
        return "\n".join(lines)

    def lower_enum(self, type_decl: Any, mod_str: str) -> str:
        name = getattr(type_decl, "name", "Unknown")
        constants = getattr(type_decl, "enum_constants", [])
        
        lines = [f"{mod_str}enum {name}", "{"]
        for c in constants:
            lines.append(f"    {c},")
        lines.append("}")
        return "\n".join(lines)
