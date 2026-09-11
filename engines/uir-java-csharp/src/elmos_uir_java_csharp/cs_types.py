from __future__ import annotations
from typing import Any

class JavaToCsTypeMapper:
    def map_type(self, uir_type: Any) -> str:
        kind = getattr(uir_type, "KIND", type(uir_type).__name__)
        
        if kind == "PrimitiveType":
            name = getattr(uir_type, "name", "")
            if name == "boolean": return "bool"
            elif name in ("int", "long", "short", "byte", "double", "float", "char", "void"):
                return name
            return name
            
        elif kind == "ClassType":
            name = getattr(uir_type, "name", "")
            if name == "String": return "string"
            elif name == "Object": return "object"
            return self.map_collection(uir_type)
            
        elif kind == "ArrayType":
            element = getattr(uir_type, "element", None)
            if element:
                return f"{self.map_type(element)}[]"
            return "object[]"
            
        return "object"

    def map_collection(self, uir_type: Any) -> str:
        name = getattr(uir_type, "name", "")
        args = getattr(uir_type, "args", [])
        
        if name == "List":
            if args:
                return f"List<{self.map_type(args[0])}>"
            return "List<object>"
        elif name == "Map":
            if len(args) == 2:
                k = self.map_type(args[0])
                v = self.map_type(args[1])
                return f"Dictionary<{k}, {v}>"
            return "Dictionary<object, object>"
        elif name == "Optional":
            if args:
                return f"{self.map_type(args[0])}?"
            return "object?"
            
        if args:
            mapped_args = ", ".join(self.map_type(a) for a in args)
            return f"{name}<{mapped_args}>"
            
        return name
