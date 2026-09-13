from __future__ import annotations
from .models import Language, FieldType

class TypeMapper:
    def map_field_type(self, field_type: FieldType, language: Language) -> str:
        mapping = {
            FieldType.STRING: {Language.JAVA: "String", Language.PYTHON: "str", Language.TYPESCRIPT: "string", Language.CSHARP: "string", Language.GO: "string"},
            FieldType.INT: {Language.JAVA: "int", Language.PYTHON: "int", Language.TYPESCRIPT: "number", Language.CSHARP: "int", Language.GO: "int"},
            FieldType.FLOAT: {Language.JAVA: "double", Language.PYTHON: "float", Language.TYPESCRIPT: "number", Language.CSHARP: "double", Language.GO: "float64"},
            FieldType.BOOLEAN: {Language.JAVA: "boolean", Language.PYTHON: "bool", Language.TYPESCRIPT: "boolean", Language.CSHARP: "bool", Language.GO: "bool"},
            FieldType.DATE: {Language.JAVA: "LocalDate", Language.PYTHON: "date", Language.TYPESCRIPT: "Date", Language.CSHARP: "DateTime", Language.GO: "time.Time"},
            FieldType.DATETIME: {Language.JAVA: "LocalDateTime", Language.PYTHON: "datetime", Language.TYPESCRIPT: "Date", Language.CSHARP: "DateTime", Language.GO: "time.Time"},
            FieldType.UUID: {Language.JAVA: "UUID", Language.PYTHON: "UUID", Language.TYPESCRIPT: "string", Language.CSHARP: "Guid", Language.GO: "uuid.UUID"},
            FieldType.DECIMAL: {Language.JAVA: "BigDecimal", Language.PYTHON: "Decimal", Language.TYPESCRIPT: "number", Language.CSHARP: "decimal", Language.GO: "float64"},
            FieldType.TEXT: {Language.JAVA: "String", Language.PYTHON: "str", Language.TYPESCRIPT: "string", Language.CSHARP: "string", Language.GO: "string"},
            FieldType.BLOB: {Language.JAVA: "byte[]", Language.PYTHON: "bytes", Language.TYPESCRIPT: "Buffer", Language.CSHARP: "byte[]", Language.GO: "[]byte"},
        }
        return mapping.get(field_type, {}).get(language, "String")

    def map_collection_type(self, element_type: str, collection_kind: str, language: Language) -> str:
        if language == Language.JAVA:
            if collection_kind == "LIST": return f"List<{element_type}>"
        elif language == Language.PYTHON:
            if collection_kind == "LIST": return f"list[{element_type}]"
        elif language == Language.TYPESCRIPT:
            if collection_kind == "LIST": return f"{element_type}[]"
        elif language == Language.CSHARP:
            if collection_kind == "LIST": return f"List<{element_type}>"
        elif language == Language.GO:
            if collection_kind == "LIST": return f"[]{element_type}"
        return f"List<{element_type}>"

    def map_nullable(self, type_str: str, language: Language) -> str:
        if language == Language.PYTHON: return f"Optional[{type_str}]"
        if language == Language.TYPESCRIPT: return f"{type_str} | null"
        if language == Language.CSHARP: return f"{type_str}?"
        if language == Language.GO: return f"*{type_str}"
        return type_str
