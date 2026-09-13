import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from elmos_mature_platform.types import (
    ApiChangeKind,
    ApiEndpointSpec,
    ApiCompatibilityAssessment,
    SdkVersionMatrix
)

class PublicApiCompatibilityEngine:
    """Engine for public API compatibility analysis, breaking change detection, and SDK version matrices."""

    def __init__(self):
        self._endpoints: Dict[str, ApiEndpointSpec] = {}  # endpoint_id -> ApiEndpointSpec
        self._sdk_matrices: Dict[str, SdkVersionMatrix] = {}  # matrix_id -> SdkVersionMatrix
        self._assessments: Dict[str, ApiCompatibilityAssessment] = {}

    def register_endpoint_spec(self, spec: ApiEndpointSpec) -> str:
        """Register an API endpoint specification."""
        if spec.endpoint_id in self._endpoints:
            raise ValueError(f"Endpoint {spec.endpoint_id} already registered")
        self._endpoints[spec.endpoint_id] = spec
        return spec.endpoint_id

    def get_endpoint_spec(self, endpoint_id: str) -> Optional[ApiEndpointSpec]:
        """Retrieve an endpoint specification by ID."""
        return self._endpoints.get(endpoint_id)

    def list_endpoint_specs(self, version: Optional[str] = None) -> List[ApiEndpointSpec]:
        """List endpoint specifications, optionally filtered by API version."""
        if version is None:
            return list(self._endpoints.values())
        return [ep for ep in self._endpoints.values() if ep.version == version]

    def deprecate_endpoint(self, endpoint_id: str, deprecated_in: str, removal_in: str) -> ApiEndpointSpec:
        """Mark an endpoint as deprecated with deprecation and removal versions."""
        ep = self.get_endpoint_spec(endpoint_id)
        if not ep:
            raise ValueError(f"Endpoint {endpoint_id} not found")
        ep.is_deprecated = True
        ep.deprecated_in = deprecated_in
        ep.removal_in = removal_in
        return ep

    def compare_endpoints(self, base_spec: ApiEndpointSpec, target_spec: ApiEndpointSpec) -> ApiCompatibilityAssessment:
        """Compare two versions of an endpoint to determine breaking/non-breaking changes."""
        breaking_changes = []
        change_kind = ApiChangeKind.NON_BREAKING

        # Check HTTP method mismatch
        if base_spec.method != target_spec.method:
            breaking_changes.append(f"HTTP method changed from {base_spec.method} to {target_spec.method}")

        # Check path mismatch
        if base_spec.path != target_spec.path:
            breaking_changes.append(f"Path changed from {base_spec.path} to {target_spec.path}")

        # Check parameter removals or type changes
        for param, p_type in base_spec.parameters.items():
            if param not in target_spec.parameters:
                breaking_changes.append(f"Parameter '{param}' removed")
            elif target_spec.parameters[param] != p_type:
                breaking_changes.append(f"Parameter '{param}' type changed from {p_type} to {target_spec.parameters[param]}")

        # Check required new parameters
        for param, p_type in target_spec.parameters.items():
            if param not in base_spec.parameters:
                if "required" in p_type.lower():
                    breaking_changes.append(f"New required parameter '{param}' added")

        # Check response schema change
        if base_spec.response_schema_hash and target_spec.response_schema_hash:
            if base_spec.response_schema_hash != target_spec.response_schema_hash:
                breaking_changes.append("Response schema altered")

        # Determine classification
        if breaking_changes:
            change_kind = ApiChangeKind.BREAKING
        elif target_spec.is_deprecated and not base_spec.is_deprecated:
            change_kind = ApiChangeKind.DEPRECATION

        assessment = ApiCompatibilityAssessment(
            assessment_id=str(uuid.uuid4()),
            base_version=base_spec.version,
            target_version=target_spec.version,
            change_kind=change_kind,
            endpoint_id=target_spec.endpoint_id,
            breaking_changes=breaking_changes,
            compatible=len(breaking_changes) == 0,
            assessed_at=datetime.now(timezone.utc).isoformat(),
            notes=f"Found {len(breaking_changes)} breaking changes" if breaking_changes else "Fully backward compatible"
        )
        self._assessments[assessment.assessment_id] = assessment
        return assessment

    def assess_version_compatibility(self, base_version: str, target_version: str) -> List[ApiCompatibilityAssessment]:
        """Assess compatibility across all endpoints between two platform/API versions."""
        base_eps = {f"{ep.method} {ep.path}": ep for ep in self.list_endpoint_specs(base_version)}
        target_eps = {f"{ep.method} {ep.path}": ep for ep in self.list_endpoint_specs(target_version)}

        results = []

        # Compare matching endpoints
        for key, base_ep in base_eps.items():
            if key in target_eps:
                target_ep = target_eps[key]
                results.append(self.compare_endpoints(base_ep, target_ep))
            else:
                # Endpoint was removed in target version!
                assessment = ApiCompatibilityAssessment(
                    assessment_id=str(uuid.uuid4()),
                    base_version=base_version,
                    target_version=target_version,
                    change_kind=ApiChangeKind.BREAKING,
                    endpoint_id=base_ep.endpoint_id,
                    breaking_changes=[f"Endpoint {key} was deleted in {target_version}"],
                    compatible=False,
                    assessed_at=datetime.now(timezone.utc).isoformat(),
                    notes="Endpoint removal is a breaking change"
                )
                self._assessments[assessment.assessment_id] = assessment
                results.append(assessment)

        # Check newly added endpoints
        for key, target_ep in target_eps.items():
            if key not in base_eps:
                assessment = ApiCompatibilityAssessment(
                    assessment_id=str(uuid.uuid4()),
                    base_version=base_version,
                    target_version=target_version,
                    change_kind=ApiChangeKind.NON_BREAKING,
                    endpoint_id=target_ep.endpoint_id,
                    breaking_changes=[],
                    compatible=True,
                    assessed_at=datetime.now(timezone.utc).isoformat(),
                    notes=f"New endpoint {key} introduced"
                )
                self._assessments[assessment.assessment_id] = assessment
                results.append(assessment)

        return results

    def register_sdk_version(self, matrix: SdkVersionMatrix) -> str:
        """Register SDK version compatibility entry."""
        if matrix.matrix_id in self._sdk_matrices:
            raise ValueError(f"SDK Matrix {matrix.matrix_id} already registered")
        self._sdk_matrices[matrix.matrix_id] = matrix
        return matrix.matrix_id

    def get_sdk_support(self, platform_version: str, language: Optional[str] = None) -> List[SdkVersionMatrix]:
        """Get supported SDK versions for a given platform version."""
        supported = []
        for m in self._sdk_matrices.values():
            if not m.supported:
                continue
            if language and m.language.lower() != language.lower():
                continue
            if m.platform_version == platform_version or (
                (not m.min_platform_version or m.min_platform_version <= platform_version) and
                (not m.max_platform_version or m.max_platform_version >= platform_version)
            ):
                supported.append(m)
        return supported

    def is_sdk_supported(self, platform_version: str, language: str, sdk_version: str) -> bool:
        """Check if a specific SDK version is supported on a platform version."""
        for m in self.get_sdk_support(platform_version, language):
            if m.sdk_version == sdk_version:
                return m.supported
        return False

    def generate_compatibility_summary(self, base_version: str, target_version: str) -> Dict[str, Any]:
        """Generate high-level compatibility summary between two API versions."""
        assessments = self.assess_version_compatibility(base_version, target_version)
        total = len(assessments)
        breaking = [a for a in assessments if not a.compatible]
        deprecations = [a for a in assessments if a.change_kind == ApiChangeKind.DEPRECATION]

        return {
            "base_version": base_version,
            "target_version": target_version,
            "total_endpoints_evaluated": total,
            "compatible": len(breaking) == 0,
            "breaking_count": len(breaking),
            "deprecation_count": len(deprecations),
            "breaking_endpoint_ids": [a.endpoint_id for a in breaking],
            "breaking_details": [
                {"endpoint_id": a.endpoint_id, "changes": a.breaking_changes} for a in breaking
            ]
        }
