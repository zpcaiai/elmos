code = """
# ─── Plane Topology Governance Models ───────────────────────────────

class PlaneFunction(str, Enum):
    CONTROL = "control"
    DATA = "data"
    MANAGEMENT = "management"
    OBSERVABILITY = "observability"
    SECURITY = "security"

class PlaneIsolation(str, Enum):
    DEDICATED = "dedicated"
    SHARED = "shared"
    HYBRID = "hybrid"

@dataclass
class PlaneDefinition:
    plane_id: str
    name: str
    function: PlaneFunction
    isolation: PlaneIsolation = PlaneIsolation.DEDICATED
    components: List[str] = field(default_factory=list)
    allowed_dependencies: List[str] = field(default_factory=list)  # plane_ids this plane may call
    forbidden_dependencies: List[str] = field(default_factory=list)
    max_latency_ms: float = 0.0
    requires_mtls: bool = False

@dataclass
class PlaneTopology:
    topology_id: str
    name: str
    plane_ids: List[str] = field(default_factory=list)
    violations: List[str] = field(default_factory=list)
    compliant: bool = False
    evaluated_at: str = ""

@dataclass
class PlaneViolation:
    violation_id: str
    source_plane: str
    target_plane: str
    rule: str  # e.g. 'forbidden_dependency', 'missing_mtls', 'circular'
    description: str = ""
    severity: str = "high"
"""
with open('/Users/stephen/DevProjects/AIProjects/elmos/engines/mature-platform-engine/src/elmos_mature_platform/types.py', 'a') as f:
    f.write("\n" + code)
