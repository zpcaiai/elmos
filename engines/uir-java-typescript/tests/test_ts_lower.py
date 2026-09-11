import pytest
from elmos_uir_java_typescript.ts_lower import TsLowerer

class DummyTypeDecl:
    KIND = "TypeDecl"
    def __init__(self, name, kind="class", modifiers=None, fields=None, methods=None, enum_constants=None):
        self.name = name
        self.kind = kind
        self.modifiers = modifiers or []
        self.fields = fields or []
        self.methods = methods or []
        self.enum_constants = enum_constants or []

def test_lower_class():
    lowerer = TsLowerer()
    c = DummyTypeDecl(name="MyClass", modifiers=["public"])
    code = lowerer.lower_type_decl(c)
    assert "export class MyClass" in code

def test_lower_interface():
    lowerer = TsLowerer()
    i = DummyTypeDecl(name="MyInterface", kind="interface")
    code = lowerer.lower_type_decl(i)
    assert "interface MyInterface" in code
