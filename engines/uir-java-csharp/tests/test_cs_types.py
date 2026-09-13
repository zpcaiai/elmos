import pytest
from elmos_uir_java_csharp.cs_types import JavaToCsTypeMapper

class DummyPrimitive:
    KIND = "PrimitiveType"
    def __init__(self, name):
        self.name = name

class DummyClass:
    KIND = "ClassType"
    def __init__(self, name, args=None):
        self.name = name
        self.args = args or []

def test_map_primitive():
    mapper = JavaToCsTypeMapper()
    assert mapper.map_type(DummyPrimitive("int")) == "int"
    assert mapper.map_type(DummyPrimitive("boolean")) == "bool"
    assert mapper.map_type(DummyPrimitive("long")) == "long"

def test_map_class():
    mapper = JavaToCsTypeMapper()
    assert mapper.map_type(DummyClass("String")) == "string"
    assert mapper.map_type(DummyClass("Object")) == "object"

def test_map_collection():
    mapper = JavaToCsTypeMapper()
    assert mapper.map_type(DummyClass("List", [DummyPrimitive("int")])) == "List<int>"
    assert mapper.map_type(DummyClass("Optional", [DummyPrimitive("int")])) == "int?"
