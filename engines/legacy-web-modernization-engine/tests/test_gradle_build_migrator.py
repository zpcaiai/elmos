"""Comprehensive unit tests for GradleBuildMigrator.

Validates deterministic Spring Boot 2.x to 3.5.3 build.gradle migration,
Java 21 toolchain injection, javax to jakarta coordinate migration,
and deprecated compile to implementation conversion.
"""

from __future__ import annotations

import unittest

from elmos_legacy_web_modernization.gradle_build_migrator import (
    GradleBuildMigrator,
    GradleMigrationResult,
)


class GradleBuildMigratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.migrator = GradleBuildMigrator()

    def test_default_version_constants(self) -> None:
        self.assertEqual(self.migrator.target_boot, "3.5.3")
        self.assertEqual(self.migrator.target_java, "21")
        self.assertEqual(self.migrator.TARGET_DEP_MGMT_VERSION, "1.1.7")

    def test_custom_target_versions(self) -> None:
        custom_migrator = GradleBuildMigrator(target_boot="3.4.1", target_java="17")
        self.assertEqual(custom_migrator.target_boot, "3.4.1")
        self.assertEqual(custom_migrator.target_java, "17")

    def test_spring_boot_plugin_version_update(self) -> None:
        content = """
plugins {
    id 'org.springframework.boot' version '2.7.14'
    id 'io.spring.dependency-management' version '1.0.15.RELEASE'
    id 'java'
}
"""
        result = self.migrator.migrate(content)
        self.assertIn("id 'org.springframework.boot' version '3.5.3'", result.migrated_content)
        self.assertIn("id 'io.spring.dependency-management' version '1.1.7'", result.migrated_content)
        self.assertIn("org.springframework.boot:3.5.3", result.plugins_updated)
        self.assertIn("io.spring.dependency-management:1.1.7", result.plugins_updated)

    def test_double_quoted_plugin_version_update(self) -> None:
        content = """
plugins {
    id "org.springframework.boot" version "2.5.4"
    id "io.spring.dependency-management" version "1.0.11.RELEASE"
}
"""
        result = self.migrator.migrate(content)
        self.assertIn('id "org.springframework.boot" version "3.5.3"', result.migrated_content)
        self.assertIn('id "io.spring.dependency-management" version "1.1.7"', result.migrated_content)

    def test_source_and_target_compatibility_update(self) -> None:
        content = """
apply plugin: 'java'

sourceCompatibility = '1.8'
targetCompatibility = '1.8'
"""
        result = self.migrator.migrate(content)
        self.assertIn("sourceCompatibility = '21'", result.migrated_content)
        self.assertIn("targetCompatibility = '21'", result.migrated_content)

    def test_java_version_enum_compatibility_update(self) -> None:
        content = """
apply plugin: 'java'

sourceCompatibility = JavaVersion.VERSION_11
targetCompatibility = JavaVersion.VERSION_11
"""
        result = self.migrator.migrate(content)
        self.assertIn("sourceCompatibility = '21'", result.migrated_content)
        self.assertIn("targetCompatibility = '21'", result.migrated_content)

    def test_javax_to_jakarta_dependency_migration(self) -> None:
        content = """
dependencies {
    implementation 'javax.servlet:javax.servlet-api'
    implementation 'javax.servlet:servlet-api'
    implementation 'javax.persistence:javax.persistence-api'
    implementation 'javax.persistence:persistence-api'
    implementation 'javax.annotation:javax.annotation-api'
    implementation 'javax.validation:validation-api'
    implementation 'javax.transaction:javax.transaction-api'
    implementation 'javax.xml.bind:jaxb-api'
}
"""
        result = self.migrator.migrate(content)
        self.assertIn("jakarta.servlet:jakarta.servlet-api:6.0.0", result.migrated_content)
        self.assertIn("jakarta.persistence:jakarta.persistence-api:3.1.0", result.migrated_content)
        self.assertIn("jakarta.annotation:jakarta.annotation-api:2.1.1", result.migrated_content)
        self.assertIn("jakarta.validation:jakarta.validation-api:3.0.2", result.migrated_content)
        self.assertIn("jakarta.transaction:jakarta.transaction-api:2.0.1", result.migrated_content)
        self.assertIn("jakarta.xml.bind:jakarta.xml.bind-api:4.0.2", result.migrated_content)
        self.assertEqual(len(result.dependencies_migrated), 8)

    def test_deprecated_compile_to_implementation(self) -> None:
        content = """
dependencies {
    compile 'org.springframework.boot:spring-boot-starter-web'
    compile "org.apache.commons:commons-lang3:3.12.0"
    testImplementation 'org.junit.jupiter:junit-jupiter'
}
"""
        result = self.migrator.migrate(content)
        self.assertNotIn("compile 'org.springframework.boot", result.migrated_content)
        self.assertIn("implementation 'org.springframework.boot:spring-boot-starter-web'", result.migrated_content)
        self.assertIn('implementation "org.apache.commons:commons-lang3:3.12.0"', result.migrated_content)
        self.assertTrue(any("Migrated deprecated 'compile'" in c for c in result.changes))

    def test_java_toolchain_block_injection(self) -> None:
        content = """
plugins {
    id 'org.springframework.boot' version '2.7.0'
    id 'java'
}
"""
        result = self.migrator.migrate(content)
        self.assertIn("java {", result.migrated_content)
        self.assertIn("toolchain {", result.migrated_content)
        self.assertIn("languageVersion = JavaLanguageVersion.of(21)", result.migrated_content)

    def test_java_toolchain_not_duplicated_if_already_present(self) -> None:
        content = """
plugins {
    id 'org.springframework.boot' version '2.7.0'
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
"""
        result = self.migrator.migrate(content)
        # Should not append a second toolchain block because JavaLanguageVersion is present
        self.assertEqual(result.migrated_content.count("toolchain {"), 1)

    def test_full_legacy_gradle_file_roundtrip(self) -> None:
        legacy_gradle = """
plugins {
    id 'org.springframework.boot' version '2.6.3'
    id 'io.spring.dependency-management' version '1.0.11.RELEASE'
    id 'java'
}

group = 'com.example'
version = '1.0.0-SNAPSHOT'
sourceCompatibility = '11'

repositories {
    mavenCentral()
}

dependencies {
    compile 'org.springframework.boot:spring-boot-starter-web'
    compile 'javax.servlet:javax.servlet-api'
    compile 'javax.persistence:javax.persistence-api'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
"""
        result = self.migrator.migrate(legacy_gradle)
        self.assertEqual(result.target_boot_version, "3.5.3")
        self.assertEqual(result.target_java_version, "21")
        self.assertIn("id 'org.springframework.boot' version '3.5.3'", result.migrated_content)
        self.assertIn("id 'io.spring.dependency-management' version '1.1.7'", result.migrated_content)
        self.assertIn("sourceCompatibility = '21'", result.migrated_content)
        self.assertIn("implementation 'org.springframework.boot:spring-boot-starter-web'", result.migrated_content)
        self.assertIn("implementation 'jakarta.servlet:jakarta.servlet-api:6.0.0'", result.migrated_content)
        self.assertIn("implementation 'jakarta.persistence:jakarta.persistence-api:3.1.0'", result.migrated_content)
        self.assertIn("languageVersion = JavaLanguageVersion.of(21)", result.migrated_content)
        self.assertTrue(len(result.changes) >= 5)


if __name__ == "__main__":
    unittest.main()
