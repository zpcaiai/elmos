import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Set
from elmos_mature_platform.types import (
    LicenseRiskLevel,
    ScaDependencyRecord,
    LicenseComplianceVerdict,
    ScaGovernanceSummary
)

class DependencyScaGovernanceEngine:
    """Engine for Software Composition Analysis (SCA) governance, license compliance, and vulnerability auditing."""

    def __init__(self):
        self._dependencies: Dict[str, ScaDependencyRecord] = {}  # dep_id -> ScaDependencyRecord
        self._project_dependencies: Dict[str, Set[str]] = {}  # project_id -> set of dep_ids
        self._verdicts: Dict[str, LicenseComplianceVerdict] = {}

        # Default classification heuristics
        self._permissive_licenses = {"MIT", "APACHE-2.0", "BSD-2-CLAUSE", "BSD-3-CLAUSE", "ISC", "UNLICENSE", "CC0-1.0"}
        self._weak_copyleft_licenses = {"LGPL-2.1", "LGPL-3.0", "MPL-2.0", "EPL-2.0"}
        self._strong_copyleft_licenses = {"GPL-2.0", "GPL-3.0", "AGPL-3.0", "SSPL-1.0"}
        self._proprietary_licenses = {"PROPRIETARY", "COMMERCIAL"}

    def classify_license_risk(self, license_spdx: str) -> LicenseRiskLevel:
        """Classify an SPDX license identifier into a risk level."""
        up = license_spdx.upper().strip()
        if up in self._permissive_licenses:
            return LicenseRiskLevel.PERMISSIVE
        elif any(up.startswith(lic) for lic in self._weak_copyleft_licenses):
            return LicenseRiskLevel.WEAK_COPYLEFT
        elif any(up.startswith(lic) for lic in self._strong_copyleft_licenses):
            return LicenseRiskLevel.STRONG_COPYLEFT
        elif up in self._proprietary_licenses:
            return LicenseRiskLevel.PROPRIETARY
        return LicenseRiskLevel.UNKNOWN

    def register_dependency(self, project_id: str, record: ScaDependencyRecord) -> str:
        """Register a software dependency under a project."""
        if record.dependency_id in self._dependencies:
            raise ValueError(f"Dependency {record.dependency_id} already registered")
        
        # Auto-classify risk if UNKNOWN
        if record.license_risk == LicenseRiskLevel.UNKNOWN and record.license_spdx:
            record.license_risk = self.classify_license_risk(record.license_spdx)

        self._dependencies[record.dependency_id] = record
        if project_id not in self._project_dependencies:
            self._project_dependencies[project_id] = set()
        self._project_dependencies[project_id].add(record.dependency_id)
        return record.dependency_id

    def get_dependency(self, dependency_id: str) -> Optional[ScaDependencyRecord]:
        """Retrieve a dependency record by ID."""
        return self._dependencies.get(dependency_id)

    def list_dependencies(self, project_id: str) -> List[ScaDependencyRecord]:
        """List all dependencies registered under a project."""
        dep_ids = self._project_dependencies.get(project_id, set())
        return [self._dependencies[did] for did in dep_ids if did in self._dependencies]

    def quarantine_dependency(self, dependency_id: str) -> ScaDependencyRecord:
        """Quarantine a dependency due to severe vulnerability or licensing violation."""
        dep = self.get_dependency(dependency_id)
        if not dep:
            raise ValueError(f"Dependency {dependency_id} not found")
        dep.is_quarantined = True
        return dep

    def unquarantine_dependency(self, dependency_id: str) -> ScaDependencyRecord:
        """Release a dependency from quarantine after remediation."""
        dep = self.get_dependency(dependency_id)
        if not dep:
            raise ValueError(f"Dependency {dependency_id} not found")
        dep.is_quarantined = False
        return dep

    def evaluate_license_compliance(
        self,
        project_id: str,
        disallowed_licenses: Optional[List[str]] = None,
        disallowed_risks: Optional[List[LicenseRiskLevel]] = None,
        reviewer: str = "system"
    ) -> LicenseComplianceVerdict:
        """Evaluate license compliance for all dependencies in a project."""
        deps = self.list_dependencies(project_id)
        disallowed_lics = set(l.upper() for l in (disallowed_licenses or []))
        disallowed_rks = set(disallowed_risks or [LicenseRiskLevel.STRONG_COPYLEFT])

        disallowed_found = []
        quarantined = []

        for dep in deps:
            if dep.is_quarantined:
                quarantined.append(dep.package_name)
            if dep.license_spdx.upper() in disallowed_lics or dep.license_risk in disallowed_rks:
                disallowed_found.append(f"{dep.package_name}@{dep.version} ({dep.license_spdx})")

        passed = len(disallowed_found) == 0 and len(quarantined) == 0

        verdict = LicenseComplianceVerdict(
            verdict_id=str(uuid.uuid4()),
            project_id=project_id,
            passed=passed,
            disallowed_licenses_found=disallowed_found,
            quarantined_packages=quarantined,
            reviewed_at=datetime.now(timezone.utc).isoformat(),
            reviewer=reviewer
        )
        self._verdicts[verdict.verdict_id] = verdict
        return verdict

    def generate_sca_summary(self, project_id: str) -> ScaGovernanceSummary:
        """Generate high-level SCA governance summary for a project."""
        deps = self.list_dependencies(project_id)
        total = len(deps)
        direct = sum(1 for d in deps if d.direct)
        transitive = total - direct
        vulnerable = sum(1 for d in deps if len(d.vulnerabilities) > 0)
        high_risk_licenses = sum(1 for d in deps if d.license_risk in {LicenseRiskLevel.STRONG_COPYLEFT, LicenseRiskLevel.UNKNOWN})
        
        # Overall compliant if no quarantined, no strong copyleft, and no reachable vulnerabilities
        reachable_vulns = sum(1 for d in deps if len(d.vulnerabilities) > 0 and d.reachable)
        overall_compliant = (high_risk_licenses == 0 and reachable_vulns == 0 and all(not d.is_quarantined for d in deps))

        return ScaGovernanceSummary(
            summary_id=str(uuid.uuid4()),
            project_id=project_id,
            total_dependencies=total,
            direct_dependencies=direct,
            transitive_dependencies=transitive,
            vulnerable_dependencies=vulnerable,
            high_risk_licenses_count=high_risk_licenses,
            overall_compliant=overall_compliant
        )

    def audit_vulnerabilities(self, project_id: str, max_allowed_cves: int = 0) -> Dict[str, Any]:
        """Audit vulnerabilities across project dependencies."""
        deps = self.list_dependencies(project_id)
        vuln_deps = [d for d in deps if len(d.vulnerabilities) > 0]
        total_cves = sum(len(d.vulnerabilities) for d in deps)
        reachable_cves = sum(len(d.vulnerabilities) for d in deps if d.reachable)

        return {
            "project_id": project_id,
            "total_dependencies": len(deps),
            "vulnerable_packages_count": len(vuln_deps),
            "total_cves": total_cves,
            "reachable_cves": reachable_cves,
            "compliant": total_cves <= max_allowed_cves,
            "vulnerable_packages": [
                {
                    "package": d.package_name,
                    "version": d.version,
                    "direct": d.direct,
                    "reachable": d.reachable,
                    "cves": d.vulnerabilities
                }
                for d in vuln_deps
            ]
        }
