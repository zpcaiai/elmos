from __future__ import annotations

from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET

from elmos_spring_modernization.enterprise_toolchain_provider import (
    EnterpriseToolchainProvider,
    MavenRepoConfig,
    MavenSettingsConfig,
    GradleToolchainConfig,
)


def test_generate_maven_settings_with_nexus_and_credentials():
    with tempfile.TemporaryDirectory() as tmpdir:
        settings_file = Path(tmpdir) / "conf" / "settings.xml"
        config = MavenSettingsConfig(
            nexus_url="https://nexus.corp.internal/repository/maven-public/",
            mirror_id="corp-nexus",
            mirror_of="*",
            username="ci-agent",
            password="corp-secret-token",
            local_repo_path="/opt/cache/m2/repository",
            offline=True,
            additional_repositories=[
                MavenRepoConfig(
                    id="corp-snapshots",
                    url="https://nexus.corp.internal/repository/maven-snapshots/",
                    snapshots_enabled=True,
                    username="ci-snapshot-user",
                    password="snapshot-secret",
                )
            ],
        )

        result_path = EnterpriseToolchainProvider.generate_maven_settings(config, settings_file)
        assert result_path.is_file()
        content = result_path.read_text(encoding="utf-8")

        # Validate that it is valid XML
        root = ET.fromstring(content)
        assert "settings" in root.tag.lower()

        # Check expected nodes
        assert "https://nexus.corp.internal/repository/maven-public/" in content
        assert "corp-nexus" in content
        assert "ci-agent" in content
        assert "corp-secret-token" in content
        assert "<localRepository>/opt/cache/m2/repository</localRepository>" in content
        assert "<offline>true</offline>" in content
        assert "corp-snapshots" in content
        assert "ci-snapshot-user" in content


def test_build_maven_cli_args():
    with tempfile.TemporaryDirectory() as tmpdir:
        settings = Path(tmpdir) / "settings.xml"
        settings.write_text("<settings/>", encoding="utf-8")
        local_repo = Path(tmpdir) / "m2"

        args = EnterpriseToolchainProvider.build_maven_cli_args(
            settings_file=settings,
            local_repo=local_repo,
            offline=True,
        )

        assert "-s" in args
        assert str(settings.resolve()) in args
        assert f"-Dmaven.repo.local={str(local_repo.resolve())}" in args
        assert "-o" in args


def test_generate_gradle_init_script():
    with tempfile.TemporaryDirectory() as tmpdir:
        init_script = Path(tmpdir) / "init.gradle"
        config = GradleToolchainConfig(
            nexus_url="https://artifactory.corp.internal/artifactory/maven-virtual",
            username="gradle-ci",
            password="gradle-password",
        )

        result_path = EnterpriseToolchainProvider.generate_gradle_init_script(config, init_script)
        assert result_path.is_file()
        content = result_path.read_text(encoding="utf-8")

        assert "https://artifactory.corp.internal/artifactory/maven-virtual" in content
        assert "gradle-ci" in content
        assert "gradle-password" in content
        assert "allprojects" in content
        assert "mavenCentral()" in content


def test_modernize_gradle_build_file():
    legacy_gradle = """
plugins {
    id 'org.springframework.boot' version '2.7.14'
    id 'java'
}

sourceCompatibility = 1.8
targetCompatibility = 1.8

dependencies {
    compile 'org.springframework.boot:spring-boot-starter-web'
    compile('org.apache.commons:commons-lang3:3.12.0')
    runtime 'com.mysql:mysql-connector-j:8.0.33'
    testCompile 'org.springframework.boot:spring-boot-starter-test'
    testRuntime 'org.junit.platform:junit-platform-launcher'
}
"""

    modernized, rules = EnterpriseToolchainProvider.modernize_gradle_build_file(legacy_gradle)

    # Validate rules triggered
    assert "RULE_GRADLE_COMPILE_TO_IMPLEMENTATION" in rules
    assert "RULE_GRADLE_TEST_COMPILE_TO_TEST_IMPLEMENTATION" in rules
    assert "RULE_GRADLE_RUNTIME_TO_RUNTIME_ONLY" in rules
    assert "RULE_GRADLE_TEST_RUNTIME_TO_TEST_RUNTIME_ONLY" in rules
    assert "RULE_GRADLE_BOOT_PLUGIN_UPGRADE_3_5_3" in rules
    assert "RULE_GRADLE_JAVA_COMPAT_TO_21" in rules

    # Validate syntax updates
    assert "version '3.5.3'" in modernized
    assert "sourceCompatibility = 21" in modernized
    assert "implementation 'org.springframework.boot:spring-boot-starter-web'" in modernized
    assert "implementation('org.apache.commons:commons-lang3:3.12.0')" in modernized
    assert "runtimeOnly 'com.mysql:mysql-connector-j:8.0.33'" in modernized
    assert "testImplementation 'org.springframework.boot:spring-boot-starter-test'" in modernized
    assert "testRuntimeOnly 'org.junit.platform:junit-platform-launcher'" in modernized


def test_modernize_gradle_wrapper():
    wrapper_props = """distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\\://services.gradle.org/distributions/gradle-6.8.3-bin.zip
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
"""

    modernized, rules = EnterpriseToolchainProvider.modernize_gradle_wrapper(wrapper_props, target_version="8.12")
    assert "RULE_GRADLE_WRAPPER_UPGRADE_8.12" in rules
    assert "gradle-8.12-bin.zip" in modernized
