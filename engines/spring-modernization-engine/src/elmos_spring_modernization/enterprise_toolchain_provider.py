from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class MavenRepoConfig:
    id: str
    url: str
    releases_enabled: bool = True
    snapshots_enabled: bool = False
    username: Optional[str] = None
    password: Optional[str] = None


@dataclass
class MavenSettingsConfig:
    nexus_url: Optional[str] = None
    mirror_id: str = "enterprise-nexus"
    mirror_of: str = "central"
    username: Optional[str] = None
    password: Optional[str] = None
    local_repo_path: Optional[str] = None
    offline: bool = False
    additional_repositories: List[MavenRepoConfig] = field(default_factory=list)


@dataclass
class GradleToolchainConfig:
    nexus_url: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    target_gradle_version: str = "8.12"
    target_java_version: int = 21


class EnterpriseToolchainProvider:
    """
    Enterprise toolchain provider for private Nexus/Artifactory mirrors,
    isolated settings.xml generation, and Gradle 4/5/6/7 to 8.x modernization.
    """

    @staticmethod
    def generate_maven_settings(config: MavenSettingsConfig, target_path: Path) -> Path:
        servers_xml = []
        mirrors_xml = []
        profiles_xml = []

        if config.nexus_url:
            if config.username and config.password:
                servers_xml.append(f"""    <server>
      <id>{config.mirror_id}</id>
      <username>{config.username}</username>
      <password>{config.password}</password>
    </server>""")

            mirrors_xml.append(f"""    <mirror>
      <id>{config.mirror_id}</id>
      <mirrorOf>{config.mirror_of}</mirrorOf>
      <url>{config.nexus_url}</url>
    </mirror>""")

        for repo in config.additional_repositories:
            if repo.username and repo.password:
                servers_xml.append(f"""    <server>
      <id>{repo.id}</id>
      <username>{repo.username}</username>
      <password>{repo.password}</password>
    </server>""")

        local_repo_tag = (
            f"  <localRepository>{config.local_repo_path}</localRepository>\n"
            if config.local_repo_path
            else ""
        )
        offline_tag = f"  <offline>{'true' if config.offline else 'false'}</offline>\n"

        servers_block = "\n".join(servers_xml)
        mirrors_block = "\n".join(mirrors_xml)

        content = f"""<settings xmlns="http://maven.apache.org/SETTINGS/1.0.0"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.0.0 https://maven.apache.org/xsd/settings-1.0.0.xsd">
{local_repo_tag}{offline_tag}  <servers>
{servers_block}
  </servers>
  <mirrors>
{mirrors_block}
  </mirrors>
</settings>
"""
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(content, encoding="utf-8")
        return target_path

    @staticmethod
    def build_maven_cli_args(
        settings_file: Optional[Path] = None,
        local_repo: Optional[Path] = None,
        offline: bool = False,
    ) -> List[str]:
        args = []
        if settings_file and settings_file.is_file():
            args.extend(["-s", str(settings_file.resolve())])
        if local_repo:
            args.append(f"-Dmaven.repo.local={str(local_repo.resolve())}")
        if offline:
            args.append("-o")
        return args

    @staticmethod
    def generate_gradle_init_script(config: GradleToolchainConfig, target_path: Path) -> Path:
        cred_block = ""
        if config.username and config.password:
            cred_block = f"""
                credentials {{
                    username = '{config.username}'
                    password = '{config.password}'
                }}"""

        repo_url = config.nexus_url or "https://repo.maven.apache.org/maven2"
        content = f"""allprojects {{
    repositories {{
        maven {{
            url '{repo_url}'{cred_block}
        }}
        mavenCentral()
    }}
}}
"""
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(content, encoding="utf-8")
        return target_path

    @staticmethod
    def modernize_gradle_build_file(content: str) -> Tuple[str, List[str]]:
        """
        Modernizes legacy Gradle build.gradle:
        - compile -> implementation
        - testCompile -> testImplementation
        - runtime -> runtimeOnly
        - testRuntime -> testRuntimeOnly
        - Spring Boot plugin 2.x -> 3.5.3
        """
        rules = []
        result = content

        # 1. Deprecated dependency configurations
        dep_replacements = [
            (r"\bcompile\s*\(", "implementation(", "RULE_GRADLE_COMPILE_TO_IMPLEMENTATION"),
            (r"\bcompile\s+['\"]", "implementation '", "RULE_GRADLE_COMPILE_TO_IMPLEMENTATION"),
            (r"\btestCompile\s*\(", "testImplementation(", "RULE_GRADLE_TEST_COMPILE_TO_TEST_IMPLEMENTATION"),
            (r"\btestCompile\s+['\"]", "testImplementation '", "RULE_GRADLE_TEST_COMPILE_TO_TEST_IMPLEMENTATION"),
            (r"\bruntime\s*\(", "runtimeOnly(", "RULE_GRADLE_RUNTIME_TO_RUNTIME_ONLY"),
            (r"\bruntime\s+['\"]", "runtimeOnly '", "RULE_GRADLE_RUNTIME_TO_RUNTIME_ONLY"),
            (r"\btestRuntime\s*\(", "testRuntimeOnly(", "RULE_GRADLE_TEST_RUNTIME_TO_TEST_RUNTIME_ONLY"),
            (r"\btestRuntime\s+['\"]", "testRuntimeOnly '", "RULE_GRADLE_TEST_RUNTIME_TO_TEST_RUNTIME_ONLY"),
        ]

        for pattern, repl, rule_name in dep_replacements:
            if re.search(pattern, result):
                result = re.sub(pattern, repl, result)
                if rule_name not in rules:
                    rules.append(rule_name)

        # 2. Spring Boot plugin version upgrade
        boot_pattern = r"(id\s*['\"]org\.springframework\.boot['\"]\s*version\s*['\"])[12]\.[0-9]+(\.[0-9]+)?(\.RELEASE)?(['\"])"
        if re.search(boot_pattern, result):
            result = re.sub(boot_pattern, r"\g<1>3.5.3\g<4>", result)
            rules.append("RULE_GRADLE_BOOT_PLUGIN_UPGRADE_3_5_3")

        # 3. Java sourceCompatibility / targetCompatibility to 21
        java_compat_pattern = r"(sourceCompatibility\s*=\s*['\"]?)1\.[8|7|6]['\"]?"
        if re.search(java_compat_pattern, result):
            result = re.sub(java_compat_pattern, r"\g<1>21", result)
            rules.append("RULE_GRADLE_JAVA_COMPAT_TO_21")

        return result, rules

    @staticmethod
    def modernize_gradle_wrapper(properties_content: str, target_version: str = "8.12") -> Tuple[str, List[str]]:
        rules = []
        result = properties_content
        dist_pattern = r"distributionUrl\s*=\s*.+gradle-([0-7]\.[0-9]+(?:\.[0-9]+)?)-(?:bin|all)\.zip"
        if re.search(dist_pattern, result):
            result = re.sub(
                dist_pattern,
                f"distributionUrl=https\\\\://services.gradle.org/distributions/gradle-{target_version}-bin.zip",
                result,
            )
            rules.append(f"RULE_GRADLE_WRAPPER_UPGRADE_{target_version}")
        return result, rules
