import pytest
from elmos_uir_java_csharp.cs_lift import CsLifter

def test_cs_lift():
    lifter = CsLifter()
    assert lifter.lift("class Foo {}") is not None
