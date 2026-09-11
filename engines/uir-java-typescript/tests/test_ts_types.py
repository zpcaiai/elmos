import pytest
from elmos_uir_java_typescript.ts_types import JavaToTsTypeMapper

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
    mapper = JavaToTsTypeMapper()
    assert mapper.map_type(DummyPrimitive("int")) == "number"
    assert mapper.map_type(DummyPrimitive("boolean")) == "boolean"
    assert mapper.map_type(DummyPrimitive("void")) == "void"

def test_map_class():
    mapper = JavaToTsTypeMapper()
    assert mapper.map_type(DummyClass("String")) == "string"
    assert mapper.map_type(DummyClass("Object")) == "unknown"

def test_map_collection():
    mapper = JavaToTsTypeMapper()
    assert mapper.map_type(DummyClass("List", [DummyPrimitive("int")])) == "number[]"
