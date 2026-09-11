from __future__ import annotations

from elmos_teaching_subsystem.project_analyzer import (
    ArchitecturePatternRecognizer,
    ProjectAnalysisService,
    TechStackFingerprinter
)

def test_architecture_pattern_recognizer():
    rec = ArchitecturePatternRecognizer()
    res = rec.analyze({})
    assert "MVC" in res
    assert "Layered" in res

def test_tech_stack_fingerprinter():
    rec = TechStackFingerprinter()
    res = rec.analyze({})
    assert res["language"] == "Python"
    assert res["framework"] == "ELMOS"

def test_project_analysis_service():
    svc = ProjectAnalysisService()
    report = svc.analyze_project({})
    assert "MVC" in report.patterns
    assert report.tech_stack["language"] == "Python"
    assert len(report.hotspots) == 1
    assert len(report.ownership) == 1
    assert len(report.apis) == 1
    assert len(report.dependencies) == 1

def test_project_analysis_with_real_files(tmp_path):
    # Setup sample Java Spring project structure
    src_dir = tmp_path / "src" / "main" / "java" / "com" / "example"
    src_dir.mkdir(parents=True)
    controllers_dir = src_dir / "controllers"
    controllers_dir.mkdir()
    services_dir = src_dir / "services"
    services_dir.mkdir()
    repositories_dir = src_dir / "repositories"
    repositories_dir.mkdir()

    # Add a controller with API mappings and TODO
    controller_file = controllers_dir / "UserController.java"
    controller_file.write_text(
        "package com.example.controllers;\n"
        "// @author alice\n"
        "import org.springframework.web.bind.annotation.*;\n"
        "@RestController\n"
        "@RequestMapping(\"/api/v1/users\")\n"
        "public class UserController {\n"
        "    // TODO: implement caching\n"
        "    @GetMapping(\"/all\")\n"
        "    public List<User> list() { return null; }\n"
        "    @PostMapping(\"/create\")\n"
        "    public void create(@RequestBody User u) {}\n"
        "}\n",
        encoding="utf-8"
    )

    # Add pom.xml
    pom_file = tmp_path / "pom.xml"
    pom_file.write_text(
        "<project>\n"
        "  <dependencies>\n"
        "    <dependency>\n"
        "      <artifactId>spring-boot-starter-web</artifactId>\n"
        "    </dependency>\n"
        "  </dependencies>\n"
        "</project>\n",
        encoding="utf-8"
    )

    svc = ProjectAnalysisService()
    report = svc.analyze_project({"root_path": str(tmp_path)})

    assert report.tech_stack["language"] == "Java"
    assert report.tech_stack["framework"] == "Spring Boot"
    assert "Repository Pattern" in report.patterns
    assert any(h["todos"] >= 1 for h in report.hotspots)
    assert any("/all" in api["endpoint"] for api in report.apis)
    assert any(d["name"] == "spring-boot-starter-web" for d in report.dependencies)
