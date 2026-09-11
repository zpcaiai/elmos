from elmos_multilang_project_generation.models import PSIR, Language, Framework, ProjectType, EntitySpec, FieldSpec, FieldType
from elmos_multilang_project_generation.generators.java_spring import JavaSpringGenerator

def test_java_spring_generation():
    psir = PSIR(
        project_name="app", description="", language=Language.JAVA, framework=Framework.SPRING_BOOT, project_type=ProjectType.REST_API,
        entities=[EntitySpec(name="User", fields=[FieldSpec(name="username", type=FieldType.STRING)])]
    )
    generator = JavaSpringGenerator()
    project = generator.generate(psir)
    assert "pom.xml" in project.files
    assert "src/main/java/com/example/entity/User.java" in project.files
    assert "@Entity" in project.files["src/main/java/com/example/entity/User.java"]
