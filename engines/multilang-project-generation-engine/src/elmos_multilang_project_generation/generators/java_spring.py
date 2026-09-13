from __future__ import annotations
from typing import Dict, Any, List
from .base import ProjectGenerator
from ..models import PSIR, GeneratedProject, EntitySpec, EndpointSpec, ServiceSpec, FieldType
from ..type_mapper import TypeMapper, Language

class JavaSpringGenerator(ProjectGenerator):
    def __init__(self):
        self.type_mapper = TypeMapper()

    def generate(self, psir: PSIR) -> GeneratedProject:
        files: Dict[str, str] = {
            "pom.xml": self.generate_build_config(psir),
            "src/main/resources/application.yml": self.generate_config(psir),
            "src/main/java/com/example/Application.java": (
                "package com.example;\n\n"
                "import org.springframework.boot.SpringApplication;\n"
                "import org.springframework.boot.autoconfigure.SpringBootApplication;\n\n"
                "@SpringBootApplication\n"
                "public class Application {\n"
                "    public static void main(String[] args) {\n"
                "        SpringApplication.run(Application.class, args);\n"
                "    }\n"
                "}\n"
            )
        }

        # Entities, Repositories, Services, Controllers
        for entity in psir.entities:
            files[f"src/main/java/com/example/entity/{entity.name}.java"] = self.generate_entity(entity)
            files[f"src/main/java/com/example/repository/{entity.name}Repository.java"] = self._generate_repository(entity)
            files[f"src/main/java/com/example/service/{entity.name}Service.java"] = self._generate_entity_service(entity)
            files[f"src/main/java/com/example/controller/{entity.name}Controller.java"] = self._generate_entity_controller(entity)

        # Standalone services
        for service in psir.services:
            svc_file = f"src/main/java/com/example/service/{service.name}.java"
            if svc_file not in files:
                files[svc_file] = self.generate_service(service)

        # Standalone endpoints
        for endpoint in psir.endpoints:
            ctrl_name = endpoint.path.strip("/").replace("/", "_").capitalize() or "Root"
            ctrl_file = f"src/main/java/com/example/controller/{ctrl_name}Controller.java"
            if ctrl_file not in files:
                files[ctrl_file] = self.generate_endpoint(endpoint)

        tests = self.generate_tests(psir)
        files.update(tests)

        return GeneratedProject(
            project_root=psir.project_name or "spring-app",
            files=files,
            build_command="mvn clean package -DskipTests=false",
            run_command="mvn spring-boot:run",
            test_command="mvn test"
        )

    def generate_entity(self, entity_spec: EntitySpec) -> str:
        fields_code = []
        getters_setters = []
        imports = {"jakarta.persistence.*"}

        for f in entity_spec.fields:
            java_type = self.type_mapper.map_field_type(f.type, Language.JAVA)
            if f.type in (FieldType.DATE, FieldType.DATETIME):
                imports.add("java.time.LocalDate" if f.type == FieldType.DATE else "java.time.LocalDateTime")
            elif f.type == FieldType.UUID:
                imports.add("java.util.UUID")
            elif f.type == FieldType.DECIMAL:
                imports.add("java.math.BigDecimal")

            col_opts = []
            if not f.required:
                col_opts.append("nullable = true")
            else:
                col_opts.append("nullable = false")
            if f.unique:
                col_opts.append("unique = true")
            col_ann = f"    @Column({', '.join(col_opts)})\n" if col_opts else ""
            fields_code.append(f"{col_ann}    private {java_type} {f.name};")

            cap_name = f.name[0].upper() + f.name[1:] if len(f.name) > 1 else f.name.upper()
            getters_setters.append(
                f"    public {java_type} get{cap_name}() {{\n        return this.{f.name};\n    }}\n\n"
                f"    public void set{cap_name}({java_type} {f.name}) {{\n        this.{f.name} = {f.name};\n    }}"
            )

        imports_str = "\n".join(f"import {imp};" for imp in sorted(imports))
        body = "\n\n".join(fields_code)
        methods = "\n\n".join(getters_setters)

        return (
            f"package com.example.entity;\n\n"
            f"{imports_str}\n\n"
            f"@Entity\n"
            f"@Table(name = \"{entity_spec.name.lower()}s\")\n"
            f"public class {entity_spec.name} {{\n\n"
            f"    @Id\n"
            f"    @GeneratedValue(strategy = GenerationType.IDENTITY)\n"
            f"    private Long id;\n\n"
            f"{body}\n\n"
            f"    public Long getId() {{\n        return this.id;\n    }}\n\n"
            f"    public void setId(Long id) {{\n        this.id = id;\n    }}\n\n"
            f"{methods}\n"
            f"}}\n"
        )

    def _generate_repository(self, entity_spec: EntitySpec) -> str:
        return (
            f"package com.example.repository;\n\n"
            f"import com.example.entity.{entity_spec.name};\n"
            f"import org.springframework.data.jpa.repository.JpaRepository;\n"
            f"import org.springframework.stereotype.Repository;\n\n"
            f"@Repository\n"
            f"public interface {entity_spec.name}Repository extends JpaRepository<{entity_spec.name}, Long> {{\n"
            f"}}\n"
        )

    def _generate_entity_service(self, entity_spec: EntitySpec) -> str:
        name = entity_spec.name
        var_name = name[0].lower() + name[1:]
        return (
            f"package com.example.service;\n\n"
            f"import com.example.entity.{name};\n"
            f"import com.example.repository.{name}Repository;\n"
            f"import org.springframework.stereotype.Service;\n"
            f"import org.springframework.transaction.annotation.Transactional;\n"
            f"import java.util.List;\n"
            f"import java.util.Optional;\n\n"
            f"@Service\n"
            f"@Transactional\n"
            f"public class {name}Service {{\n\n"
            f"    private final {name}Repository {var_name}Repository;\n\n"
            f"    public {name}Service({name}Repository {var_name}Repository) {{\n"
            f"        this.{var_name}Repository = {var_name}Repository;\n"
            f"    }}\n\n"
            f"    @Transactional(readOnly = true)\n"
            f"    public List<{name}> findAll() {{\n"
            f"        return {var_name}Repository.findAll();\n"
            f"    }}\n\n"
            f"    @Transactional(readOnly = true)\n"
            f"    public Optional<{name}> findById(Long id) {{\n"
            f"        return {var_name}Repository.findById(id);\n"
            f"    }}\n\n"
            f"    public {name} create({name} entity) {{\n"
            f"        return {var_name}Repository.save(entity);\n"
            f"    }}\n\n"
            f"    public {name} update(Long id, {name} entity) {{\n"
            f"        entity.setId(id);\n"
            f"        return {var_name}Repository.save(entity);\n"
            f"    }}\n\n"
            f"    public void delete(Long id) {{\n"
            f"        {var_name}Repository.deleteById(id);\n"
            f"    }}\n"
            f"}}\n"
        )

    def _generate_entity_controller(self, entity_spec: EntitySpec) -> str:
        name = entity_spec.name
        var_name = name[0].lower() + name[1:]
        path = f"api/{entity_spec.name.lower()}s"
        return (
            f"package com.example.controller;\n\n"
            f"import com.example.entity.{name};\n"
            f"import com.example.service.{name}Service;\n"
            f"import org.springframework.http.ResponseEntity;\n"
            f"import org.springframework.web.bind.annotation.*;\n"
            f"import java.util.List;\n\n"
            f"@RestController\n"
            f"@RequestMapping(\"/{path}\")\n"
            f"public class {name}Controller {{\n\n"
            f"    private final {name}Service {var_name}Service;\n\n"
            f"    public {name}Controller({name}Service {var_name}Service) {{\n"
            f"        this.{var_name}Service = {var_name}Service;\n"
            f"    }}\n\n"
            f"    @GetMapping\n"
            f"    public List<{name}> getAll() {{\n"
            f"        return {var_name}Service.findAll();\n"
            f"    }}\n\n"
            f"    @GetMapping(\"/{id}\")\n"
            f"    public ResponseEntity<{name}> getById(@PathVariable Long id) {{\n"
            f"        return {var_name}Service.findById(id)\n"
            f"            .map(ResponseEntity::ok)\n"
            f"            .orElse(ResponseEntity.notFound().build());\n"
            f"    }}\n\n"
            f"    @PostMapping\n"
            f"    public {name} create(@RequestBody {name} entity) {{\n"
            f"        return {var_name}Service.create(entity);\n"
            f"    }}\n\n"
            f"    @PutMapping(\"/{id}\")\n"
            f"    public {name} update(@PathVariable Long id, @RequestBody {name} entity) {{\n"
            f"        return {var_name}Service.update(id, entity);\n"
            f"    }}\n\n"
            f"    @DeleteMapping(\"/{id}\")\n"
            f"    public ResponseEntity<Void> delete(@PathVariable Long id) {{\n"
            f"        {var_name}Service.delete(id);\n"
            f"        return ResponseEntity.noContent().build();\n"
            f"    }}\n"
            f"}}\n"
        )

    def generate_endpoint(self, endpoint_spec: EndpointSpec) -> str:
        ctrl_name = endpoint_spec.path.strip("/").replace("/", "_").capitalize() or "Root"
        method_verb = endpoint_spec.method.upper()
        mapping_ann = f"@{method_verb.capitalize()}Mapping" if method_verb in ("GET", "POST", "PUT", "DELETE", "PATCH") else f"@RequestMapping(method = RequestMethod.{method_verb})"
        return (
            f"package com.example.controller;\n\n"
            f"import org.springframework.http.ResponseEntity;\n"
            f"import org.springframework.web.bind.annotation.*;\n"
            f"import java.util.Map;\n\n"
            f"@RestController\n"
            f"public class {ctrl_name}Controller {{\n\n"
            f"    {mapping_ann}(\"{endpoint_spec.path}\")\n"
            f"    public ResponseEntity<?> handle() {{\n"
            f"        return ResponseEntity.ok(Map.of(\"status\", \"ok\", \"path\", \"{endpoint_spec.path}\"));\n"
            f"    }}\n"
            f"}}\n"
        )

    def generate_service(self, service_spec: ServiceSpec) -> str:
        methods = []
        for m in service_spec.methods:
            methods.append(f"    public void {m}() {{\n        // business logic for {m}\n    }}")
        methods_str = "\n\n".join(methods) if methods else "    // No operations specified"
        return (
            f"package com.example.service;\n\n"
            f"import org.springframework.stereotype.Service;\n\n"
            f"@Service\n"
            f"public class {service_spec.name} {{\n"
            f"{methods_str}\n"
            f"}}\n"
        )

    def generate_build_config(self, psir: PSIR | None = None) -> str:
        artifact = (psir.project_name if psir else "demo").lower().replace(" ", "-")
        return (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
            "<project xmlns=\"http://maven.apache.org/POM/4.0.0\"\n"
            "         xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\"\n"
            "         xsi:schemaLocation=\"http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd\">\n"
            "  <modelVersion>4.0.0</modelVersion>\n"
            "  <parent>\n"
            "    <groupId>org.springframework.boot</groupId>\n"
            "    <artifactId>spring-boot-starter-parent</artifactId>\n"
            "    <version>3.4.0</version>\n"
            "    <relativePath/>\n"
            "  </parent>\n"
            "  <groupId>com.example</groupId>\n"
            f"  <artifactId>{artifact}</artifactId>\n"
            "  <version>0.0.1-SNAPSHOT</version>\n"
            "  <name>demo</name>\n"
            "  <description>Generated by ELMOS Project Synthesis</description>\n"
            "  <properties>\n"
            "    <java.version>21</java.version>\n"
            "  </properties>\n"
            "  <dependencies>\n"
            "    <dependency>\n"
            "      <groupId>org.springframework.boot</groupId>\n"
            "      <artifactId>spring-boot-starter-web</artifactId>\n"
            "    </dependency>\n"
            "    <dependency>\n"
            "      <groupId>org.springframework.boot</groupId>\n"
            "      <artifactId>spring-boot-starter-data-jpa</artifactId>\n"
            "    </dependency>\n"
            "    <dependency>\n"
            "      <groupId>org.springframework.boot</groupId>\n"
            "      <artifactId>spring-boot-starter-validation</artifactId>\n"
            "    </dependency>\n"
            "    <dependency>\n"
            "      <groupId>com.h2database</groupId>\n"
            "      <artifactId>h2</artifactId>\n"
            "      <scope>runtime</scope>\n"
            "    </dependency>\n"
            "    <dependency>\n"
            "      <groupId>org.springframework.boot</groupId>\n"
            "      <artifactId>spring-boot-starter-test</artifactId>\n"
            "      <scope>test</scope>\n"
            "    </dependency>\n"
            "  </dependencies>\n"
            "  <build>\n"
            "    <plugins>\n"
            "      <plugin>\n"
            "        <groupId>org.springframework.boot</groupId>\n"
            "        <artifactId>spring-boot-maven-plugin</artifactId>\n"
            "      </plugin>\n"
            "    </plugins>\n"
            "  </build>\n"
            "</project>\n"
        )

    def generate_config(self, psir: PSIR | None = None) -> str:
        app_name = (psir.project_name if psir else "app").lower()
        return (
            f"server:\n"
            f"  port: 8080\n\n"
            f"spring:\n"
            f"  application:\n"
            f"    name: {app_name}\n"
            f"  datasource:\n"
            f"    url: jdbc:h2:mem:{app_name}db;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE\n"
            f"    driver-class-name: org.h2.Driver\n"
            f"    username: sa\n"
            f"    password: \n"
            f"  jpa:\n"
            f"    hibernate:\n"
            f"      ddl-auto: update\n"
            f"    show-sql: true\n"
            f"    properties:\n"
            f"      hibernate:\n"
            f"        format_sql: true\n"
            f"  h2:\n"
            f"    console:\n"
            f"      enabled: true\n"
            f"      path: /h2-console\n"
        )

    def generate_tests(self, psir: PSIR | None = None) -> Dict[str, str]:
        return {
            "src/test/java/com/example/ApplicationTests.java": (
                "package com.example;\n\n"
                "import org.junit.jupiter.api.Test;\n"
                "import org.springframework.boot.test.context.SpringBootTest;\n\n"
                "@SpringBootTest\n"
                "class ApplicationTests {\n\n"
                "    @Test\n"
                "    void contextLoads() {\n"
                "    }\n"
                "}\n"
            )
        }
