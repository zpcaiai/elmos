from __future__ import annotations

from typing import Any

# In a real setup, we would import UIR from the Python package, 
# assuming it's available in the environment. We'll use structural ducks if needed, 
# or just define the mapper based on type class names as strings.

class JavaToTsTypeMapper:
    def map_type(self, uir_type: Any) -> str:
        kind = getattr(uir_type, "KIND", type(uir_type).__name__)
        
        if kind == "PrimitiveType":
            name = getattr(uir_type, "name", "")
            if name in ("int", "long", "short", "byte", "double", "float"):
                return "number"
            elif name == "boolean":
                return "boolean"
            elif name == "void":
                return "void"
            elif name == "char":
                return "string"
            return name
            
        elif kind == "ClassType":
            name = getattr(uir_type, "name", "")
            if name == "String":
                return "string"
            elif name == "Object":
                return "unknown"
            return self.map_collection(uir_type)
            
        elif kind == "ArrayType":
            element = getattr(uir_type, "element", None)
            if element:
                return f"{self.map_type(element)}[]"
            return "unknown[]"
            
        return "unknown"

    def map_collection(self, uir_type: Any) -> str:
        name = getattr(uir_type, "name", "")
        args = getattr(uir_type, "args", [])
        
        if name == "List":
            if args:
                return f"{self.map_type(args[0])}[]"
            return "unknown[]"
        elif name == "Map":
            if len(args) == 2:
                k = self.map_type(args[0])
                v = self.map_type(args[1])
                return f"Map<{k}, {v}>"
            return "Map<unknown, unknown>"
        elif name == "Optional":
            if args:
                return f"{self.map_type(args[0])} | undefined"
            return "unknown | undefined"
            
        # Default handling of generic args
        if args:
            mapped_args = ", ".join(self.map_type(a) for a in args)
            return f"{name}<{mapped_args}>"
            
        return name
