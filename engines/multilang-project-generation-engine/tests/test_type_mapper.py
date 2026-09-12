from elmos_multilang_project_generation.type_mapper import TypeMapper
from elmos_multilang_project_generation.models import Language, FieldType

def test_map_field_type():
    mapper = TypeMapper()
    assert mapper.map_field_type(FieldType.STRING, Language.JAVA) == "String"
    assert mapper.map_field_type(FieldType.INT, Language.PYTHON) == "int"
