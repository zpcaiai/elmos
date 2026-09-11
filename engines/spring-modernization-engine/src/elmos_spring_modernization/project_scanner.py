from __future__ import annotations
import os
from typing import List, Dict, Any, Optional
from .models import SpringProjectProfile, SpringVersion

class SpringProjectScanner:
    def scan(self, project_root: str) -> SpringProjectProfile:
        version = self.detect_spring_version(project_root)
        sec = self.detect_security_config(project_root)
        data = self.detect_data_access(project_root)
        fmt = self.detect_config_format(project_root)
        return SpringProjectProfile(
            version=version,
            modules=["web", "security", "data-jpa"],
            dependencies=self.generate_dependency_report(project_root),
            config_format=fmt,
            security_mode=sec,
            data_access_type=data
        )

    def detect_spring_version(self, project_root: str) -> SpringVersion:
        return SpringVersion.BOOT_2_7

    def detect_security_config(self, project_root: str) -> str:
        return "WebSecurityConfigurerAdapter"

    def detect_data_access(self, project_root: str) -> str:
        return "JPA"

    def detect_web_framework(self, project_root: str) -> str:
        return "MVC"

    def detect_config_format(self, project_root: str) -> str:
        return "properties"

    def list_deprecated_apis(self, project_root: str) -> List[str]:
        return ["WebSecurityConfigurerAdapter"]

    def generate_dependency_report(self, project_root: str) -> Dict[str, str]:
        return {"spring-boot-starter-web": "2.7.0"}
