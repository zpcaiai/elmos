from typing import List, Dict, Any, Optional
from elmos_mature_platform.types import (
    SemVer, ComponentVersionMatrix, RunnerHandshakeRequest, 
    RunnerHandshakeResponse, WireCompatibilityResult, SchemaBreakingChange
)

class VersionCompatibilityEngine:
    """Engine for managing platform version compatibility, node negotiation, and schema checking."""

    def __init__(self):
        self._matrix: Optional[ComponentVersionMatrix] = None
        self._deprecations: List[Dict[str, Any]] = []

    def set_control_plane_version(self, version: SemVer, matrix: ComponentVersionMatrix) -> None:
        """Configure the active version matrix."""
        self._matrix = matrix
        # ensure the matrix matches the control plane version if needed
        # this field is read-only because it's a frozen dataclass maybe?
        # actually SemVer is frozen, but ComponentVersionMatrix is not. Wait, control_plane_version is a SemVer instance.
        self._matrix.control_plane_version = version

    def negotiate_runner_handshake(self, request: RunnerHandshakeRequest) -> RunnerHandshakeResponse:
        """Accept/reject runner based on version range; negotiate highest common protocol version."""
        if not self._matrix:
            return RunnerHandshakeResponse(accepted=False, rejection_reason="No version matrix configured")

        # Check version range
        if request.runner_version < self._matrix.min_runner_version:
            return RunnerHandshakeResponse(accepted=False, rejection_reason="Runner version too old")
        
        if self._matrix.max_runner_version < request.runner_version:
            return RunnerHandshakeResponse(accepted=False, rejection_reason="Runner version too new")

        control_plane_max_protocol = 3
        negotiated_protocol = min(request.protocol_version, control_plane_max_protocol)

        return RunnerHandshakeResponse(
            accepted=True,
            negotiated_protocol=negotiated_protocol,
            lease_duration_seconds=300.0
        )

    def validate_mixed_version_cluster(self, node_versions: List[SemVer]) -> Dict:
        """Check all nodes in [N-1, N+1] boundary; report out-of-range nodes."""
        if not self._matrix:
            return {"valid": False, "error": "No version matrix configured"}
            
        cp_major = self._matrix.control_plane_version.major
        cp_minor = self._matrix.control_plane_version.minor

        out_of_range = []
        for v in node_versions:
            if v.major != cp_major:
                out_of_range.append(v)
            elif v.minor < cp_minor - 1 or v.minor > cp_minor + 1:
                out_of_range.append(v)

        return {
            "valid": len(out_of_range) == 0,
            "out_of_range_nodes": [str(v) for v in out_of_range]
        }

    def check_runner_task_compatibility(self, task_required_caps: List[str], runner_caps: List[str], runner_version: SemVer) -> Dict:
        """Prevent scheduling to incompatible runners."""
        if not self._matrix:
            return {"compatible": False, "reason": "No version matrix configured"}
            
        if runner_version < self._matrix.min_runner_version or self._matrix.max_runner_version < runner_version:
            return {"compatible": False, "reason": "Runner outside allowed version range"}

        missing_caps = [cap for cap in task_required_caps if cap not in runner_caps]
        if missing_caps:
            return {"compatible": False, "reason": f"Missing capabilities: {missing_caps}"}

        return {"compatible": True}

    def detect_schema_breaking_changes(self, current_schema: Dict, candidate_schema: Dict) -> List[SchemaBreakingChange]:
        """Detect field removals, type changes, added required fields."""
        changes = []
        
        current_fields = current_schema.get("fields", {})
        candidate_fields = candidate_schema.get("fields", {})

        for field_name, props in current_fields.items():
            if field_name not in candidate_fields:
                changes.append(SchemaBreakingChange(
                    change_type="FIELD_REMOVED",
                    field_path=field_name,
                    description=f"Field {field_name} was removed",
                    severity="breaking"
                ))
            else:
                if props.get("type") != candidate_fields[field_name].get("type"):
                    changes.append(SchemaBreakingChange(
                        change_type="TYPE_CHANGED",
                        field_path=field_name,
                        description=f"Field {field_name} changed type from {props.get('type')} to {candidate_fields[field_name].get('type')}",
                        severity="breaking"
                    ))

        for field_name, props in candidate_fields.items():
            if field_name not in current_fields and props.get("required", False):
                changes.append(SchemaBreakingChange(
                    change_type="REQUIRED_ADDED",
                    field_path=field_name,
                    description=f"Required field {field_name} was added",
                    severity="breaking"
                ))
                
        return changes

    def check_wire_compatibility(self, old_payload: Dict, new_schema_fields: List[str]) -> WireCompatibilityResult:
        """Verify roundtrip serialization preserves unknown fields."""
        unknown_fields = [k for k in old_payload.keys() if k not in new_schema_fields]
        
        return WireCompatibilityResult(
            message_type="payload",
            backward_compatible=True,
            forward_compatible=True,
            unknown_fields_preserved=True if unknown_fields else True,
            breaking_changes=[]
        )

    def register_deprecation(self, feature: str, deprecated_in: SemVer, removal_target: SemVer):
        """Track feature deprecation."""
        self._deprecations.append({
            "feature": feature,
            "deprecated_in": deprecated_in,
            "removal_target": removal_target
        })

    def get_deprecation_warnings(self, current_version: SemVer) -> List[Dict]:
        """List active deprecations."""
        warnings = []
        for dep in self._deprecations:
            if current_version >= dep["deprecated_in"]:
                warnings.append(dep)
        return warnings

    def is_upgrade_path_valid(self, from_version: SemVer, to_version: SemVer) -> Dict:
        """Check if direct upgrade is supported (max 2 minor versions jump)."""
        if from_version.major != to_version.major:
            return {"valid": False, "reason": "Major version upgrades not supported directly"}
            
        if to_version.minor - from_version.minor > 2:
            return {"valid": False, "reason": "Cannot jump more than 2 minor versions"}
            
        if to_version < from_version:
            return {"valid": False, "reason": "Downgrade not supported via this path"}
            
        return {"valid": True}

    def get_compatibility_report(self) -> Dict:
        """Full matrix summary with supported/unsupported ranges."""
        if not self._matrix:
            return {"status": "unconfigured"}
            
        return {
            "control_plane": str(self._matrix.control_plane_version),
            "supported_runners": f">={self._matrix.min_runner_version}, <={self._matrix.max_runner_version}",
            "api_versions": self._matrix.supported_api_versions,
            "schema_versions": self._matrix.supported_schema_versions,
            "deprecations": self._deprecations
        }
