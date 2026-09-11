from __future__ import annotations
from typing import Dict, Any
from .base import ProjectGenerator
from ..models import PSIR, GeneratedProject, EntitySpec, EndpointSpec, ServiceSpec

class JavaSpringGenerator(ProjectGenerator):
    def generate(self, psir: PSIR) -> GeneratedProject:
        files = {
            "pom.xml": self.generate_build_config(),
            "src/main/java/com/example/Application.java": "package com.example;\n\nimport org.springframework.boot.SpringApplication;\nimport org.springframework.boot.autoconfigure.SpringBootApplication;\n\n@SpringBootApplication\npublic class Application {\n    public static void main(String[] args) {\n        SpringApplication.run(Application.class, args);\n    }\n}\n",
            "src/main/resources/application.yml": self.generate_config()
        }
        for entity in psir.entities:
            files[f"src/main/java/com/example/entity/{entity.name}.java"] = self.generate_entity(entity)
        for endpoint in psir.endpoints:
            files[f"src/main/java/com/example/controller/{endpoint.path.strip('/').capitalize()}Controller.java"] = self.generate_endpoint(endpoint)
        for service in psir.services:
            files[f"src/main/java/com/example/service/{service.name}.java"] = self.generate_service(service)
        
        tests = self.generate_tests()
        files.update(tests)
            
        return GeneratedProject(
            project_root=psir.project_name,
            files=files,
            build_command="mvn clean install",
            run_command="mvn spring-boot:run",
            test_command="mvn test"
        )

    def generate_entity(self, entity_spec: EntitySpec) -> str:
        fields_str = "\n    ".join([f"private String {f.name};" for f in entity_spec.fields])
        return f"package com.example.entity;\n\nimport jakarta.persistence.*;\n\n@Entity\n@Table(name = \"{entity_spec.name.lower()}\")\npublic class {entity_spec.name} {{\n    @Id\n    @GeneratedValue(strategy = GenerationType.IDENTITY)\n    private Long id;\n\n    {{fields_str}}\n}}\n".replace("{{fields_str}}", fields_str)

    def generate_endpoint(self, endpoint_spec: EndpointSpec) -> str:
        return f"package com.example.controller;\n\nimport org.springframework.web.bind.annotation.*;\n\n@RestController\npublic class ApiController {{\n    @RequestMapping(method = RequestMethod.{endpoint_spec.method.upper()}, path = \"{endpoint_spec.path}\")\n    public Object handle() {{\n        return null;\n    }}\n}}\n"

    def generate_service(self, service_spec: ServiceSpec) -> str:
        methods = "\n    ".join([f"public void {m}() {{}}" for m in service_spec.methods])
        return f"package com.example.service;\n\nimport org.springframework.stereotype.Service;\n\n@Service\npublic class {service_spec.name} {{\n    {{methods}}\n}}\n".replace("{{methods}}", methods)

    def generate_build_config(self) -> str:
        return "<project>\n  <modelVersion>4.0.0</modelVersion>\n  <groupId>com.example</groupId>\n  <artifactId>demo</artifactId>\n  <version>0.0.1-SNAPSHOT</version>\n</project>"

    def generate_config(self) -> str:
        return "spring:\n  application:\n    name: demo\n"

    def generate_tests(self) -> Dict[str, str]:
        return {"src/test/java/com/example/ApplicationTests.java": "package com.example;\n\nimport org.junit.jupiter.api.Test;\nimport org.springframework.boot.test.context.SpringBootTest;\n\n@SpringBootTest\nclass ApplicationTests {\n    @Test\n    void contextLoads() {\n    }\n}\n"}
