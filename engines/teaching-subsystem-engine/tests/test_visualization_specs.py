import pytest
from elmos_teaching_subsystem.visualization_specs import D3SpecGenerator

def test_d3_spec_generator():
    gen = D3SpecGenerator()
    res = gen.generate_force_graph([{"id": 1}], [])
    assert "nodes" in res
    assert "links" in res
