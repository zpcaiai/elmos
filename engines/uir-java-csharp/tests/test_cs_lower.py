import pytest
from elmos_uir_java_csharp.cs_lower import CsLowerer

class DummyTypeDecl:
    KIND = "TypeDecl"
    def __init__(self, name, kind="class", modifiers=None, fields=None, methods=None, enum_constants=None, superclass=None, interfaces=None):
        self.name = name
        self.kind = kind
        self.modifiers = modifiers or []
        self.fields = fields or []
        self.methods = methods or []
        self.enum_constants = enum_constants or []
        self.superclass = superclass
        self.interfaces = interfaces or []

class DummyClass:
    KIND = "ClassType"
    def __init__(self, name):
        self.name = name

def test_lower_class():
    lowerer = CsLowerer()
    c = DummyTypeDecl(name="MyClass", modifiers=["public", "final"], superclass=DummyClass("Base"))
    code = lowerer.lower_type_decl(c)
    assert "public sealed class MyClass : Base" in code

def test_lower_interface():
    lowerer = CsLowerer()
    i = DummyTypeDecl(name="MyInterface", kind="interface", modifiers=["public"])
    code = lowerer.lower_type_decl(i)
    assert "public interface IMyInterface" in code
