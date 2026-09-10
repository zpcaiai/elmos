import uuid
from typing import Dict, List, Optional
from elmos_mature_platform.types import (
    PlatformComponent,
    VersionEntry,
    CompatibilityRecord,
    CompatibilityStatus
)

class PlatformVersionCompatibilityEngine:
    def __init__(self):
        self._versions: Dict[PlatformComponent, Dict[str, VersionEntry]] = {
            component: {} for component in PlatformComponent
        }
        # A dictionary mapping component pairs and version pairs to a record
        self._records: Dict[str, CompatibilityRecord] = {}

    def _get_pair_key(self, comp_a: PlatformComponent, ver_a: str, comp_b: PlatformComponent, ver_b: str) -> str:
        # Canonicalize the pair to always look up consistently
        if comp_a < comp_b or (comp_a == comp_b and ver_a <= ver_b):
            return f"{comp_a}:{ver_a}:{comp_b}:{ver_b}"
        return f"{comp_b}:{ver_b}:{comp_a}:{ver_a}"

    def register_version(self, entry: VersionEntry) -> str:
        """Registers a platform component version."""
        self._versions[entry.component][entry.version] = entry
        return f"{entry.component.value}:{entry.version}"

    def record_compatibility(self, record: CompatibilityRecord) -> str:
        """Records a compatibility result between two component versions."""
        if not record.record_id:
            record.record_id = str(uuid.uuid4())
        key = self._get_pair_key(record.component_a, record.version_a, record.component_b, record.version_b)
        self._records[key] = record
        return record.record_id

    def check_compatibility(
        self, component_a: PlatformComponent, version_a: str, component_b: PlatformComponent, version_b: str
    ) -> CompatibilityStatus:
        """Looks up the compatibility status between two component versions."""
        # 1. Check explicit records
        key = self._get_pair_key(component_a, version_a, component_b, version_b)
        if key in self._records:
            return self._records[key].status

        # 2. Check min_compatible_versions
        entry_a = self._versions[component_a].get(version_a)
        entry_b = self._versions[component_b].get(version_b)
        
        # Helper to parse semantic versions for comparison (simple split by .)
        def parse_ver(v: str) -> tuple:
            try:
                return tuple(int(x) for x in v.split('.'))
            except ValueError:
                return (0,)

        # Check A's restrictions on B
        if entry_a and component_b in entry_a.min_compatible_versions:
            min_v = entry_a.min_compatible_versions[component_b]
            if parse_ver(version_b) < parse_ver(min_v):
                return CompatibilityStatus.INCOMPATIBLE

        # Check B's restrictions on A
        if entry_b and component_a in entry_b.min_compatible_versions:
            min_v = entry_b.min_compatible_versions[component_a]
            if parse_ver(version_a) < parse_ver(min_v):
                return CompatibilityStatus.INCOMPATIBLE

        return CompatibilityStatus.UNTESTED

    def get_compatible_versions(self, component: PlatformComponent, version: str) -> Dict[PlatformComponent, List[str]]:
        """Finds all compatible versions of other components for a given component version."""
        result: Dict[PlatformComponent, List[str]] = {comp: [] for comp in PlatformComponent if comp != component}
        
        for other_comp in result.keys():
            for other_ver in self._versions[other_comp].keys():
                if self.check_compatibility(component, version, other_comp, other_ver) == CompatibilityStatus.COMPATIBLE:
                    result[other_comp].append(other_ver)
        return result

    def detect_breaking_changes(self, component: PlatformComponent, from_version: str, to_version: str) -> List[str]:
        """Detects breaking changes across a version upgrade path."""
        def parse_ver(v: str) -> tuple:
            try:
                return tuple(int(x) for x in v.split('.'))
            except ValueError:
                return (0,)

        start = parse_ver(from_version)
        end = parse_ver(to_version)
        
        breaking_changes = []
        for ver, entry in self._versions[component].items():
            ver_tuple = parse_ver(ver)
            if start < ver_tuple <= end:
                breaking_changes.extend(entry.breaking_changes)
        
        return breaking_changes

    def get_upgrade_path(self, component: PlatformComponent, from_version: str, to_version: str) -> List[str]:
        """Calculates an ordered upgrade path if minor/patch upgrades are required before major."""
        def parse_ver(v: str) -> tuple:
            try:
                return tuple(int(x) for x in v.split('.'))
            except ValueError:
                return (0,)

        start = parse_ver(from_version)
        end = parse_ver(to_version)
        
        if start >= end:
            return []

        # Simple logic: order all versions between start and end
        versions = []
        for ver in self._versions[component].keys():
            ver_tuple = parse_ver(ver)
            if start < ver_tuple <= end:
                versions.append((ver_tuple, ver))
                
        versions.sort(key=lambda x: x[0])
        return [v[1] for v in versions]

    def get_eol_versions(self) -> List[VersionEntry]:
        """Retrieves all versions marked as unsupported or having an EOL date."""
        eol_entries = []
        for comp_versions in self._versions.values():
            for entry in comp_versions.values():
                if not entry.supported or entry.eol_date:
                    eol_entries.append(entry)
        return eol_entries

    def get_version_matrix(self, components: List[PlatformComponent]) -> Dict:
        """Builds a cross-component compatibility matrix for a set of components."""
        matrix = {}
        for comp_a in components:
            matrix[comp_a] = {}
            for ver_a in self._versions[comp_a].keys():
                matrix[comp_a][ver_a] = {}
                for comp_b in components:
                    if comp_a == comp_b:
                        continue
                    matrix[comp_a][ver_a][comp_b] = {}
                    for ver_b in self._versions[comp_b].keys():
                        status = self.check_compatibility(comp_a, ver_a, comp_b, ver_b)
                        matrix[comp_a][ver_a][comp_b][ver_b] = status.value
        return matrix

    def validate_deployment(self, versions: Dict[str, str]) -> Dict:
        """
        Validates a full deployment map of (component -> version), 
        checking all-pairs compatibility.
        """
        issues = []
        is_valid = True
        
        comps = list(versions.keys())
        for i in range(len(comps)):
            for j in range(i + 1, len(comps)):
                c1 = PlatformComponent(comps[i])
                v1 = versions[comps[i]]
                c2 = PlatformComponent(comps[j])
                v2 = versions[comps[j]]
                
                status = self.check_compatibility(c1, v1, c2, v2)
                if status in (CompatibilityStatus.INCOMPATIBLE, CompatibilityStatus.DEPRECATED):
                    is_valid = False
                    issues.append(f"{c1.value}@{v1} and {c2.value}@{v2} are {status.value}")
                elif status == CompatibilityStatus.UNTESTED:
                    issues.append(f"{c1.value}@{v1} and {c2.value}@{v2} are untested")

        return {
            "valid": is_valid,
            "issues": issues
        }

    def get_compatibility_report(self) -> Dict:
        """Returns statistics on versions and compatibility testing."""
        total_versions = sum(len(v) for v in self._versions.values())
        total_records = len(self._records)
        compatible = sum(1 for r in self._records.values() if r.status == CompatibilityStatus.COMPATIBLE)
        incompatible = sum(1 for r in self._records.values() if r.status == CompatibilityStatus.INCOMPATIBLE)
        
        return {
            "total_versions": total_versions,
            "tested_pairs": total_records,
            "compatible_pairs": compatible,
            "incompatible_pairs": incompatible,
            "compatibility_percentage": (compatible / total_records * 100) if total_records > 0 else 0.0
        }
