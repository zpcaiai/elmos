"""Deterministic Gradle build modernizer for Spring Boot migrations.

Migrates legacy Spring Boot 2.x / Spring MVC build.gradle to Spring Boot 3.5.3
on Java 21, performing AST/regex-safe dependency replacements, plugin updates,
and toolchain configuration with full auditability and zero silent drops.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class GradleMigrationResult:
    original_content: str
    migrated_content: str
    changes: tuple[str, ...]
    plugins_updated: tuple[str, ...]
    dependencies_migrated: tuple[str, ...]
    target_boot_version: str = "3.5.3"
    target_java_version: str = "21"


class GradleBuildMigrator:
    TARGET_BOOT_VERSION = "3.5.3"
    TARGET_JAVA_VERSION = "21"
    TARGET_DEP_MGMT_VERSION = "1.1.7"

    DEPENDENCY_MAPPINGS = {
        "javax.servlet:javax.servlet-api": "jakarta.servlet:jakarta.servlet-api:6.0.0",
        "javax.servlet:servlet-api": "jakarta.servlet:jakarta.servlet-api:6.0.0",
        "javax.persistence:javax.persistence-api": "jakarta.persistence:jakarta.persistence-api:3.1.0",
        "javax.persistence:persistence-api": "jakarta.persistence:jakarta.persistence-api:3.1.0",
        "javax.annotation:javax.annotation-api": "jakarta.annotation:jakarta.annotation-api:2.1.1",
        "javax.validation:validation-api": "jakarta.validation:jakarta.validation-api:3.0.2",
        "javax.transaction:javax.transaction-api": "jakarta.transaction:jakarta.transaction-api:2.0.1",
        "javax.xml.bind:jaxb-api": "jakarta.xml.bind:jakarta.xml.bind-api:4.0.2",
    }

    def __init__(self, target_boot: str = TARGET_BOOT_VERSION, target_java: str = TARGET_JAVA_VERSION):
        self.target_boot = target_boot
        self.target_java = target_java

    def migrate(self, content: str) -> GradleMigrationResult:
        changes: list[str] = []
        plugins_updated: list[str] = []
        deps_migrated: list[str] = []

        migrated = content

        # 1. Update Spring Boot plugin version
        boot_plugin_pattern = r"(id\s*['\"]org\.springframework\.boot['\"]\s*version\s*['\"])([^'\"]+)(['\"])"
        if re.search(boot_plugin_pattern, migrated):
            old_ver = re.search(boot_plugin_pattern, migrated).group(2)
            migrated = re.sub(
                boot_plugin_pattern,
                rf"\g<1>{self.target_boot}\g<3>",
                migrated,
            )
            changes.append(f"Updated org.springframework.boot plugin version from {old_ver} to {self.target_boot}")
            plugins_updated.append(f"org.springframework.boot:{self.target_boot}")

        # 2. Update dependency-management plugin version
        dep_mgmt_pattern = r"(id\s*['\"]io\.spring\.dependency-management['\"]\s*version\s*['\"])([^'\"]+)(['\"])"
        if re.search(dep_mgmt_pattern, migrated):
            old_dm_ver = re.search(dep_mgmt_pattern, migrated).group(2)
            migrated = re.sub(
                dep_mgmt_pattern,
                rf"\g<1>{self.TARGET_DEP_MGMT_VERSION}\g<3>",
                migrated,
            )
            changes.append(f"Updated io.spring.dependency-management plugin version from {old_dm_ver} to {self.TARGET_DEP_MGMT_VERSION}")
            plugins_updated.append(f"io.spring.dependency-management:{self.TARGET_DEP_MGMT_VERSION}")

        # 3. Update sourceCompatibility and targetCompatibility
        compat_pattern = r"(sourceCompatibility|targetCompatibility)\s*=\s*['\"]?(\d+(?:\.\d+)?|JavaVersion\.[A-Za-z0-9_]+)['\"]?"
        for match in re.finditer(compat_pattern, migrated):
            prop, old_val = match.group(1), match.group(2)
            changes.append(f"Updated {prop} from {old_val} to '{self.target_java}'")
        migrated = re.sub(
            r"sourceCompatibility\s*=\s*['\"]?(\d+(?:\.\d+)?|JavaVersion\.[A-Za-z0-9_]+)['\"]?",
            f"sourceCompatibility = '{self.target_java}'",
            migrated,
        )
        migrated = re.sub(
            r"targetCompatibility\s*=\s*['\"]?(\d+(?:\.\d+)?|JavaVersion\.[A-Za-z0-9_]+)['\"]?",
            f"targetCompatibility = '{self.target_java}'",
            migrated,
        )

        # 4. Migrate javax dependencies to jakarta
        for old_coord, new_coord in self.DEPENDENCY_MAPPINGS.items():
            if old_coord in migrated:
                migrated = migrated.replace(old_coord, new_coord)
                changes.append(f"Migrated dependency: {old_coord} -> {new_coord}")
                deps_migrated.append(new_coord)

        # 5. Migrate 'compile ' to 'implementation ' if deprecated syntax is found
        if re.search(r"^\s*compile\s+['\"]", migrated, re.MULTILINE):
            migrated = re.sub(r"^(\s*)compile(\s+['\"])", r"\1implementation\2", migrated, flags=re.MULTILINE)
            changes.append("Migrated deprecated 'compile' configuration to 'implementation'")

        # 6. Ensure Java toolchain block exists if java plugin is configured
        if "apply plugin: 'java'" in migrated or "id 'java'" in migrated or "id 'org.springframework.boot'" in migrated:
            if "JavaLanguageVersion" not in migrated:
                toolchain_block = (
                    f"\njava {{\n"
                    f"    toolchain {{\n"
                    f"        languageVersion = JavaLanguageVersion.of({self.target_java})\n"
                    f"    }}\n"
                    f"}}\n"
                )
                migrated += toolchain_block
                changes.append(f"Configured Java toolchain languageVersion = {self.target_java}")

        return GradleMigrationResult(
            original_content=content,
            migrated_content=migrated,
            changes=tuple(changes),
            plugins_updated=tuple(plugins_updated),
            dependencies_migrated=tuple(deps_migrated),
            target_boot_version=self.target_boot,
            target_java_version=self.target_java,
        )
