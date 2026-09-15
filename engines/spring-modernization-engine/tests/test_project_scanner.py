from elmos_spring_modernization.project_scanner import SpringProjectScanner
from elmos_spring_modernization.models import SpringVersion

def test_scan(tmp_path):
    pom = tmp_path / "pom.xml"
    pom.write_text("""<project xmlns="http://maven.apache.org/POM/4.0.0">
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>2.7.18</version>
    </parent>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
    </dependencies>
</project>""", encoding="utf-8")

    src = tmp_path / "src" / "main" / "java" / "com" / "example"
    src.mkdir(parents=True)
    (src / "SecurityConfig.java").write_text("""
package com.example;
import org.springframework.security.config.annotation.web.configuration.WebSecurityConfigurerAdapter;
public class SecurityConfig extends WebSecurityConfigurerAdapter {}
""", encoding="utf-8")

    resources = tmp_path / "src" / "main" / "resources"
    resources.mkdir(parents=True)
    (resources / "application.yml").write_text("server:\n  port: 8080\n", encoding="utf-8")

    scanner = SpringProjectScanner()
    profile = scanner.scan(str(tmp_path))

    assert profile.version == SpringVersion.BOOT_2_7
    assert profile.security_mode == "WebSecurityConfigurerAdapter"
    assert profile.data_access_type == "JPA"
    assert profile.config_format == "yaml"
    assert "spring-boot-starter-web" in profile.dependencies
    assert "spring-boot-starter-data-jpa" in profile.dependencies

    deprecated = scanner.list_deprecated_apis(str(tmp_path))
    assert "WebSecurityConfigurerAdapter" in deprecated
