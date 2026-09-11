import pytest
from elmos_uir_java_typescript.ts_lift import TsLifter

def test_ts_lift():
    lifter = TsLifter()
    assert lifter.lift("class Foo {}") is not None
