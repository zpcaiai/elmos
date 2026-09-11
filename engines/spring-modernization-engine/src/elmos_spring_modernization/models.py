from __future__ import annotations
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

class SpringVersion(Enum):
    BOOT_1_5 = "1.5"
    BOOT_2_0 = "2.0"
    BOOT_2_7 = "2.7"
    BOOT_3_0 = "3.0"
    BOOT_3_2 = "3.2"
    BOOT_3_5 = "3.5"
    BOOT_4_0 = "4.0"

class MigrationCategory(Enum):
    NAMESPACE = auto()
    DEPENDENCY = auto()
    CONFIGURATION = auto()
    SECURITY = auto()
    DATA_ACCESS = auto()
    WEB = auto()
    TESTING = auto()
    BUILD = auto()

class RiskLevel(Enum):
    LOW = auto()
    MEDIUM = auto()
    HIGH = auto()
    CRITICAL = auto()

@dataclass
class MigrationRule:
    rule_id: str
    name: str
    description: str
    source_pattern: str
    target_pattern: str
    category: MigrationCategory
    risk_level: RiskLevel
    auto_applicable: bool = True

@dataclass
class ModernizationTarget:
    source_version: SpringVersion
    target_version: SpringVersion
    modules: List[str]
    options: Dict[str, Any]

@dataclass
class FileChange:
    file_path: str
    change_type: str  # MODIFY, CREATE, DELETE
    description: str
    diff_preview: str

@dataclass
class MigrationPlan:
    plan_id: str
    source_version: SpringVersion
    target_version: SpringVersion
    rules: List[MigrationRule]
    estimated_changes: int
    risk_summary: Dict[RiskLevel, int]

@dataclass
class MigrationResult:
    plan_id: str
    applied_rules: List[str]
    skipped_rules: List[str]
    failed_rules: List[str]
    file_changes: List[FileChange]
    warnings: List[str]

@dataclass
class SpringProjectProfile:
    version: SpringVersion
    modules: List[str]
    dependencies: Dict[str, str]
    config_format: str
    security_mode: str
    data_access_type: str
