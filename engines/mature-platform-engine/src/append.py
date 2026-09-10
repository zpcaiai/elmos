import os
types_path = "/Users/stephen/DevProjects/AIProjects/elmos/engines/mature-platform-engine/src/elmos_mature_platform/types.py"

content = """

# ─── Deployment Matrix Certification Models ──────────────────────────

class DeploymentEnvironment(str, Enum):
    DEV = "dev"
    STAGING = "staging"
    PRODUCTION = "production"
    DR = "dr"
    EDGE = "edge"

class CertificationStatus(str, Enum):
    NOT_TESTED = "not_tested"
    IN_PROGRESS = "in_progress"
    PASSED = "passed"
    FAILED = "failed"
    WAIVED = "waived"

@dataclass
class DeploymentCell:
    cell_id: str
    environment: DeploymentEnvironment
    platform: str  # kubernetes, ecs, vm, bare_metal
    region: str
    version: str
    status: CertificationStatus = CertificationStatus.NOT_TESTED
    test_count: int = 0
    pass_count: int = 0
    fail_count: int = 0
    last_tested: str = ""
    certified_by: str = ""
    waiver_reason: str = ""

@dataclass
class DeploymentMatrix:
    matrix_id: str
    product_name: str
    version: str
    cells: List[str] = field(default_factory=list)  # cell_ids
    required_environments: List[str] = field(default_factory=list)
    required_platforms: List[str] = field(default_factory=list)
    overall_status: CertificationStatus = CertificationStatus.NOT_TESTED
    coverage_pct: float = 0.0
    created_at: str = ""

@dataclass
class MatrixTestResult:
    result_id: str
    cell_id: str
    test_name: str
    passed: bool
    duration_seconds: float = 0.0
    error_message: str = ""
    timestamp: str = ""
"""

with open(types_path, "a") as f:
    f.write(content)
