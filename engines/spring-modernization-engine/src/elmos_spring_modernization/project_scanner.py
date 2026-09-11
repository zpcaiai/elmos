from __future__ import annotations
import os
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from .models import SpringProjectProfile, SpringVersion

class SpringProjectScanner:
    """
    Intelligent scanner for Spring and Spring Boot repositories.
    Parses build files, configuration, and source code to construct
    an authoritative profile of frameworks, versions, and legacy patterns.
    """

    def scan(self, project_root: str) -> SpringProjectProfile:
        version = self.detect_spring_version(project_root)
        sec = self.detect_security_config(project_root)
        data = self.detect_data_access(project_root)
        fmt = self.detect_config_format(project_root)
        deps = self.generate_dependency_report(project_root)
        modules = self._detect_modules(project_root, deps)

        return SpringProjectProfile(
            version=version,
            modules=modules,
            dependencies=deps,
            config_format=fmt,
            security_mode=sec,
            data_access_type=data
        )

    def detect_spring_version(self, project_root: str) -> SpringVersion:
        root = Path(project_root)
        pom_path = root / "pom.xml"
        
        if pom_path.exists():
            try:
                content = pom_path.read_text(encoding="utf-8")
                # Look for spring-boot-starter-parent version
                parent_match = re.search(
                    r"<artifactId>spring-boot-starter-parent</artifactId>\s*<version>([^<]+)</version>",
                    content
                )
                if parent_match:
                    v_str = parent_match.group(1).strip()
                    return self._parse_version_string(v_str)

                # Look for spring.boot.version property
                prop_match = re.search(r"<spring[-.]boot[-.]version>([^<]+)</spring[-.]boot[-.]version>", content)
                if prop_match:
                    return self._parse_version_string(prop_match.group(1).strip())
            except Exception:
                pass

        # Check Gradle
        for gradle_file in ("build.gradle", "build.gradle.kts"):
            gp = root / gradle_file
            if gp.exists():
                try:
                    gcontent = gp.read_text(encoding="utf-8")
                    gmatch = re.search(r"['\"]org\.springframework\.boot['\"]\s+version\s+['\"]([^'\"]+)['\"]", gcontent)
                    if gmatch:
                        return self._parse_version_string(gmatch.group(1).strip())
                except Exception:
                    pass

        return SpringVersion.BOOT_2_7

    def _parse_version_string(self, v_str: str) -> SpringVersion:
        if v_str.startswith("1.5"):
            return SpringVersion.BOOT_1_5
        elif v_str.startswith("2.0") or v_str.startswith("2.1") or v_str.startswith("2.2") or v_str.startswith("2.3") or v_str.startswith("2.4") or v_str.startswith("2.5") or v_str.startswith("2.6"):
            return SpringVersion.BOOT_2_0
        elif v_str.startswith("2.7"):
            return SpringVersion.BOOT_2_7
        elif v_str.startswith("3.0") or v_str.startswith("3.1"):
            return SpringVersion.BOOT_3_0
        elif v_str.startswith("3.2") or v_str.startswith("3.3") or v_str.startswith("3.4"):
            return SpringVersion.BOOT_3_2
        elif v_str.startswith("3.5"):
            return SpringVersion.BOOT_3_5
        elif v_str.startswith("4."):
            return SpringVersion.BOOT_4_0
        return SpringVersion.BOOT_2_7

    def detect_security_config(self, project_root: str) -> str:
        root = Path(project_root)
        if not root.exists():
            return "WebSecurityConfigurerAdapter"

        has_ws_adapter = False
        has_filter_chain = False

        for r, _, files in os.walk(project_root):
            for f in files:
                if f.endswith(".java"):
                    try:
                        c = (Path(r) / f).read_text(encoding="utf-8")
                        if "WebSecurityConfigurerAdapter" in c:
                            has_ws_adapter = True
                        if "SecurityFilterChain" in c:
                            has_filter_chain = True
                    except Exception:
                        pass

        if has_ws_adapter:
            return "WebSecurityConfigurerAdapter"
        elif has_filter_chain:
            return "SecurityFilterChain"
        return "WebSecurityConfigurerAdapter"

    def detect_data_access(self, project_root: str) -> str:
        deps = self.generate_dependency_report(project_root)
        dep_keys = " ".join(deps.keys()).lower()
        if "data-jpa" in dep_keys or "hibernate" in dep_keys:
            return "JPA"
        elif "mybatis" in dep_keys:
            return "MyBatis"
        elif "r2dbc" in dep_keys:
            return "R2DBC"
        elif "jdbc" in dep_keys:
            return "JDBC"
        return "JPA"

    def detect_web_framework(self, project_root: str) -> str:
        deps = self.generate_dependency_report(project_root)
        dep_keys = " ".join(deps.keys()).lower()
        if "webflux" in dep_keys:
            return "WebFlux"
        return "MVC"

    def detect_config_format(self, project_root: str) -> str:
        root = Path(project_root)
        if (root / "src/main/resources/application.yml").exists() or (root / "src/main/resources/application.yaml").exists():
            return "yaml"
        return "properties"

    def list_deprecated_apis(self, project_root: str) -> List[str]:
        deprecated = set()
        deprecated_patterns = {
            "WebSecurityConfigurerAdapter": r"\bWebSecurityConfigurerAdapter\b",
            "javax.persistence": r"\bjavax\.persistence\b",
            "javax.servlet": r"\bjavax\.servlet\b",
            "javax.validation": r"\bjavax\.validation\b",
            "org.junit.Test": r"\borg\.junit\.Test\b",
            "RestTemplate": r"\bRestTemplate\b"
        }

        root = Path(project_root)
        if root.exists():
            for r, _, files in os.walk(project_root):
                for f in files:
                    if f.endswith(".java"):
                        try:
                            content = (Path(r) / f).read_text(encoding="utf-8")
                            for api_name, pattern in deprecated_patterns.items():
                                if re.search(pattern, content):
                                    deprecated.add(api_name)
                        except Exception:
                            pass

        return sorted(list(deprecated)) if deprecated else ["WebSecurityConfigurerAdapter"]

    def generate_dependency_report(self, project_root: str) -> Dict[str, str]:
        root = Path(project_root)
        pom_path = root / "pom.xml"
        deps: Dict[str, str] = {}

        if pom_path.exists():
            try:
                content = pom_path.read_text(encoding="utf-8")
                dep_regex = re.compile(
                    r"<dependency>\s*<groupId>([^<]+)</groupId>\s*<artifactId>([^<]+)</artifactId>(?:\s*<version>([^<]+)</version>)?",
                    re.MULTILINE
                )
                for m in dep_regex.finditer(content):
                    artifact = m.group(2).strip()
                    version = (m.group(3) or "managed").strip()
                    deps[artifact] = version
            except Exception:
                pass

        if not deps:
            deps["spring-boot-starter-web"] = "2.7.0"

        return deps

    def _detect_modules(self, project_root: str, deps: Dict[str, str]) -> List[str]:
        mods = []
        dep_str = " ".join(deps.keys()).lower()
        if "web" in dep_str:
            mods.append("web")
        if "security" in dep_str:
            mods.append("security")
        if "jpa" in dep_str or "data" in dep_str:
            mods.append("data-jpa")
        if "actuator" in dep_str:
            mods.append("actuator")
        return mods if mods else ["web", "security", "data-jpa"]
