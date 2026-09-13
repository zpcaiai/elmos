from elmos_multilang_project_generation.psir_parser import PSIRParser

def test_parse_yaml():
    parser = PSIRParser()
    yaml_content = "project_name: test\nlanguage: PYTHON\nframework: FASTAPI\nproject_type: REST_API"
    psir = parser.parse_yaml(yaml_content)
    assert psir.project_name == "test"
