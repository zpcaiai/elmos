from typing import List, Dict, Optional, Any
from datetime import datetime
import uuid

from elmos_mature_platform.types import (
    ApiCompatChangeType,
    CompatibilityVerdict,
    ApiChange,
    SdkCompatibilityMatrix,
    EventSchemaChange,
    CompatibilityGateResult
)

class ApiCompatibilityGateEngine:
    def __init__(self) -> None:
        self._api_versions: Dict[str, List[Dict]] = {}
        self._sdks: List[SdkCompatibilityMatrix] = []
        self._deprecations: Dict[str, Dict[str, str]] = {}
    
    def register_api_version(self, version: str, endpoints: List[Dict]) -> None:
        """Register API version with a list of endpoint definitions."""
        self._api_versions[version] = endpoints

    def compare_api_versions(self, old_version: str, new_version: str) -> List[ApiChange]:
        """Detect changes between API versions."""
        if old_version not in self._api_versions or new_version not in self._api_versions:
            raise ValueError("Version not registered")
        
        old_eps = {ep.get('path', ''): ep for ep in self._api_versions[old_version]}
        new_eps = {ep.get('path', ''): ep for ep in self._api_versions[new_version]}
        
        changes = []
        
        # Check added and modified endpoints
        for path, new_ep in new_eps.items():
            if path not in old_eps:
                changes.append(ApiChange(
                    change_id=str(uuid.uuid4()),
                    change_type=ApiCompatChangeType.ENDPOINT_ADDED,
                    path=path,
                    description=f"Endpoint {path} added",
                    verdict=CompatibilityVerdict.COMPATIBLE
                ))
            else:
                old_ep = old_eps[path]
                
                # Check fields
                old_fields = old_ep.get('fields', {})
                new_fields = new_ep.get('fields', {})
                
                for fname, ftype in new_fields.items():
                    if fname not in old_fields:
                        if new_ep.get('required_fields', []) and fname in new_ep['required_fields']:
                            changes.append(ApiChange(
                                change_id=str(uuid.uuid4()),
                                change_type=ApiCompatChangeType.REQUIRED_FIELD_ADDED,
                                path=f"{path}, field: {fname}",
                                description=f"Required field {fname} added",
                                verdict=CompatibilityVerdict.BREAKING
                            ))
                        else:
                            changes.append(ApiChange(
                                change_id=str(uuid.uuid4()),
                                change_type=ApiCompatChangeType.FIELD_ADDED,
                                path=f"{path}, field: {fname}",
                                description=f"Optional field {fname} added",
                                verdict=CompatibilityVerdict.COMPATIBLE
                            ))
                    else:
                        if old_fields[fname] != ftype:
                            changes.append(ApiChange(
                                change_id=str(uuid.uuid4()),
                                change_type=ApiCompatChangeType.FIELD_TYPE_CHANGED,
                                path=f"{path}, field: {fname}",
                                description=f"Field {fname} type changed from {old_fields[fname]} to {ftype}",
                                verdict=CompatibilityVerdict.BREAKING
                            ))
                
                for fname in old_fields:
                    if fname not in new_fields:
                        changes.append(ApiChange(
                            change_id=str(uuid.uuid4()),
                            change_type=ApiCompatChangeType.FIELD_REMOVED,
                            path=f"{path}, field: {fname}",
                            description=f"Field {fname} removed",
                            verdict=CompatibilityVerdict.BREAKING
                        ))
        
        # Check removed endpoints
        for path, old_ep in old_eps.items():
            if path not in new_eps:
                changes.append(ApiChange(
                    change_id=str(uuid.uuid4()),
                    change_type=ApiCompatChangeType.ENDPOINT_REMOVED,
                    path=path,
                    description=f"Endpoint {path} removed",
                    verdict=CompatibilityVerdict.BREAKING
                ))
        
        return changes

    def evaluate_compatibility_gate(self, changes: List[ApiChange]) -> CompatibilityGateResult:
        """Gate: FAIL if any breaking changes without migration guide, or removed endpoints without prior deprecation."""
        breaking = 0
        compatible = 0
        deprecated = 0
        blocking = []
        warnings = []
        
        for change in changes:
            if change.verdict == CompatibilityVerdict.BREAKING:
                breaking += 1
                if not change.migration_guide:
                    blocking.append(change)
                if change.change_type == ApiCompatChangeType.ENDPOINT_REMOVED:
                    dep = self._deprecations.get(change.path)
                    if not dep:
                        blocking.append(change)
                    else:
                        warnings.append(f"Endpoint {change.path} removed. Deprecated since {dep['deprecated_in']}")
            elif change.verdict == CompatibilityVerdict.COMPATIBLE:
                compatible += 1
            elif change.verdict == CompatibilityVerdict.DEPRECATED:
                deprecated += 1
        
        # Ensure unique blocking
        unique_blocking = {c.change_id: c for c in blocking}.values()
        
        return CompatibilityGateResult(
            gate_id=str(uuid.uuid4()),
            passed=len(unique_blocking) == 0,
            total_changes=len(changes),
            breaking_changes=breaking,
            compatible_changes=compatible,
            deprecated_changes=deprecated,
            blocking_changes=list(unique_blocking),
            warnings=warnings
        )

    def register_sdk(self, matrix: SdkCompatibilityMatrix) -> None:
        """Register SDK with API version support."""
        self._sdks.append(matrix)

    def check_sdk_impact(self, api_changes: List[ApiChange]) -> List[Dict]:
        """Which SDKs are affected by breaking changes."""
        impacted = []
        breaking = [c for c in api_changes if c.verdict == CompatibilityVerdict.BREAKING]
        if not breaking:
            return impacted
        
        # Simplified: all SDKs might be affected if they rely on breaking paths
        for sdk in self._sdks:
            affected_paths = [c.path for c in breaking]
            impacted.append({
                "sdk_name": sdk.sdk_name,
                "sdk_version": sdk.sdk_version,
                "affected_changes": affected_paths
            })
            sdk.breaking_changes_affected.extend(affected_paths)
            
        return impacted

    def detect_event_schema_changes(self, old_schema: Dict, new_schema: Dict, event_type: str) -> List[EventSchemaChange]:
        """Event contract breaking changes."""
        changes = []
        
        old_fields = old_schema.get("properties", {})
        new_fields = new_schema.get("properties", {})
        
        for fname, ftype in new_fields.items():
            if fname not in old_fields:
                is_req = fname in new_schema.get("required", [])
                if is_req:
                    changes.append(EventSchemaChange(
                        event_type=event_type,
                        field_path=fname,
                        change=ApiCompatChangeType.REQUIRED_FIELD_ADDED,
                        backward_compatible=False,
                        forward_compatible=True
                    ))
                else:
                    changes.append(EventSchemaChange(
                        event_type=event_type,
                        field_path=fname,
                        change=ApiCompatChangeType.FIELD_ADDED,
                        backward_compatible=True,
                        forward_compatible=True
                    ))
            elif old_fields[fname] != ftype:
                changes.append(EventSchemaChange(
                    event_type=event_type,
                    field_path=fname,
                    change=ApiCompatChangeType.FIELD_TYPE_CHANGED,
                    backward_compatible=False,
                    forward_compatible=False
                ))
        
        for fname in old_fields:
            if fname not in new_fields:
                changes.append(EventSchemaChange(
                    event_type=event_type,
                    field_path=fname,
                    change=ApiCompatChangeType.FIELD_REMOVED,
                    backward_compatible=True,
                    forward_compatible=False
                ))
                
        return changes

    def register_deprecation(self, api_path: str, deprecated_in: str, removal_version: str, migration_guide: str) -> None:
        """Track API deprecation."""
        self._deprecations[api_path] = {
            "deprecated_in": deprecated_in,
            "removal_version": removal_version,
            "migration_guide": migration_guide
        }

    def get_active_deprecations(self) -> List[Dict]:
        """List all active deprecations."""
        return [
            {"api_path": k, **v} for k, v in self._deprecations.items()
        ]

    def validate_removal(self, api_path: str, current_version: str) -> Dict:
        """Check if enough deprecation notice was given before removal."""
        dep = self._deprecations.get(api_path)
        if not dep:
            return {
                "valid": False,
                "reason": "No prior deprecation notice found"
            }
        
        # Simplified string comparison for versions
        if current_version < dep["removal_version"]:
            return {
                "valid": False,
                "reason": f"Removed in {current_version} before planned removal version {dep['removal_version']}"
            }
            
        return {
            "valid": True,
            "reason": "Adequate deprecation notice given"
        }

    def generate_migration_guide(self, old_version: str, new_version: str) -> Dict:
        """Auto-generate migration guide from changes."""
        changes = self.compare_api_versions(old_version, new_version)
        guide = {
            "from_version": old_version,
            "to_version": new_version,
            "steps": []
        }
        
        for change in changes:
            if change.change_type == ApiCompatChangeType.ENDPOINT_REMOVED:
                dep = self._deprecations.get(change.path)
                mg = dep["migration_guide"] if dep else "No automatic migration available."
                guide["steps"].append(f"Endpoint {change.path} removed: {mg}")
            elif change.verdict == CompatibilityVerdict.BREAKING:
                guide["steps"].append(f"Breaking change at {change.path}: {change.description}. {change.migration_guide}")
                
        return guide

    def get_compatibility_report(self) -> Dict:
        """Summary across all versions."""
        return {
            "versions_registered": list(self._api_versions.keys()),
            "total_sdks_registered": len(self._sdks),
            "active_deprecations": len(self._deprecations)
        }
