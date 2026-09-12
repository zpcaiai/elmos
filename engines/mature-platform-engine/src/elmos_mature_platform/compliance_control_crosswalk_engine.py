"""Compliance Control Crosswalk Engine (Batch 40 - Skill 1381).

Cross-maps security and privacy compliance controls across major frameworks:
SOC2 Type 2, ISO 27001, HIPAA, PCI-DSS, NIST-CSF, GDPR, and FedRAMP.
Performs automated gap analyses and determines reciprocal compliance coverage.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from elmos_mature_platform.types import (
    ComplianceFramework,
    ControlCrosswalkRecord,
    CrosswalkGapAnalysis,
    CrosswalkMappingType,
)


class ComplianceControlCrosswalkEngine:
    """Industrial engine for cross-framework compliance control crosswalk (B40)."""

    def __init__(self):
        self._mappings: Dict[str, ControlCrosswalkRecord] = {}
        self._audit_log: List[Dict[str, Any]] = []
        self._seed_standard_crosswalks()

    def _seed_standard_crosswalks(self) -> None:
        """Seed foundational crosswalk mappings across major frameworks."""
        seeds = [
            # SOC2 CC6.1 (Logical Access) <-> ISO27001 A.9.1.1 (Access Control Policy)
            ControlCrosswalkRecord(
                mapping_id="map-soc2-iso-access",
                source_framework=ComplianceFramework.SOC2_TYPE2,
                source_control_id="CC6.1",
                target_framework=ComplianceFramework.ISO27001,
                target_control_id="A.9.1.1",
                mapping_type=CrosswalkMappingType.EXACT_EQUIVALENT,
                rationale="Both mandate defined logical access boundaries and RBAC",
            ),
            # SOC2 CC6.6 (Encryption in Transit) <-> PCI-DSS Req 4.1
            ControlCrosswalkRecord(
                mapping_id="map-soc2-pci-tls",
                source_framework=ComplianceFramework.SOC2_TYPE2,
                source_control_id="CC6.6",
                target_framework=ComplianceFramework.PCI_DSS,
                target_control_id="Req-4.1",
                mapping_type=CrosswalkMappingType.EXACT_EQUIVALENT,
                rationale="Both require TLS 1.3/AES-256 encryption in transit across public networks",
            ),
            # ISO27001 A.12.1.2 (Change Management) <-> NIST-CSF PR.IP-3
            ControlCrosswalkRecord(
                mapping_id="map-iso-nist-change",
                source_framework=ComplianceFramework.ISO27001,
                source_control_id="A.12.1.2",
                target_framework=ComplianceFramework.NIST_CSF,
                target_control_id="PR.IP-3",
                mapping_type=CrosswalkMappingType.SUPERSET,
                rationale="ISO27001 change control encompasses configuration change tracking",
            ),
            # GDPR Art 32 (Security of Processing) <-> HIPAA 164.312(a)(1) (Technical Safeguards)
            ControlCrosswalkRecord(
                mapping_id="map-gdpr-hipaa-safeguards",
                source_framework=ComplianceFramework.GDPR,
                source_control_id="Art-32",
                target_framework=ComplianceFramework.HIPAA,
                target_control_id="164.312",
                mapping_type=CrosswalkMappingType.PARTIAL_OVERLAP,
                rationale="Both enforce encryption, integrity controls, and disaster recovery access",
            ),
            # NIST-CSF PR.DS-1 (Data at Rest) <-> FedRAMP SC-28
            ControlCrosswalkRecord(
                mapping_id="map-nist-fedramp-crypto",
                source_framework=ComplianceFramework.NIST_CSF,
                source_control_id="PR.DS-1",
                target_framework=ComplianceFramework.FedRAMP,
                target_control_id="SC-28",
                mapping_type=CrosswalkMappingType.EXACT_EQUIVALENT,
                rationale="Both specify FIPS-validated cryptographic protection of data at rest",
            ),
        ]
        for m in seeds:
            self._mappings[m.mapping_id] = m

    def add_mapping(self, mapping: ControlCrosswalkRecord) -> str:
        """Register a new crosswalk record."""
        self._mappings[mapping.mapping_id] = mapping
        self._record_audit("mapping_added", mapping.mapping_id, {
            "source": mapping.source_framework.value,
            "target": mapping.target_framework.value,
        })
        return mapping.mapping_id

    def get_mappings(
        self,
        source_framework: Optional[ComplianceFramework] = None,
        target_framework: Optional[ComplianceFramework] = None,
    ) -> List[ControlCrosswalkRecord]:
        """Query mappings with optional source and target framework filters."""
        res = list(self._mappings.values())
        if source_framework:
            res = [m for m in res if m.source_framework == source_framework]
        if target_framework:
            res = [m for m in res if m.target_framework == target_framework]
        return res

    def find_equivalent_controls(
        self,
        from_framework: ComplianceFramework,
        control_id: str,
        to_framework: ComplianceFramework,
    ) -> List[ControlCrosswalkRecord]:
        """Find bidirectional mapped controls between two frameworks."""
        matches: List[ControlCrosswalkRecord] = []
        for m in self._mappings.values():
            # Forward match
            if (m.source_framework == from_framework and
                m.source_control_id == control_id and
                m.target_framework == to_framework):
                matches.append(m)
            # Reverse match if equivalent or superset/subset
            elif (m.target_framework == from_framework and
                  m.target_control_id == control_id and
                  m.source_framework == to_framework):
                matches.append(m)
        return matches

    def perform_gap_analysis(
        self,
        from_framework: ComplianceFramework,
        to_framework: ComplianceFramework,
        implemented_source_controls: List[str],
        all_target_controls: List[str],
    ) -> CrosswalkGapAnalysis:
        """Analyze how many target controls are already covered by implemented source controls."""
        covered_targets = set()
        for src_ctrl in implemented_source_controls:
            equivs = self.find_equivalent_controls(from_framework, src_ctrl, to_framework)
            for eq in equivs:
                if eq.source_framework == from_framework:
                    covered_targets.add(eq.target_control_id)
                else:
                    covered_targets.add(eq.source_control_id)

        target_set = set(all_target_controls)
        actually_covered = target_set.intersection(covered_targets)
        gaps = sorted(list(target_set - covered_targets))

        cov_pct = round((len(actually_covered) / len(target_set)) * 100.0, 2) if target_set else 100.0

        analysis = CrosswalkGapAnalysis(
            analysis_id=f"gap-{uuid.uuid4().hex[:8]}",
            from_framework=from_framework,
            to_framework=to_framework,
            covered_controls_count=len(actually_covered),
            gap_controls=gaps,
            crosswalk_coverage_pct=cov_pct,
        )

        self._record_audit("gap_analysis_performed", analysis.analysis_id, {
            "from": from_framework.value,
            "to": to_framework.value,
            "coverage_pct": cov_pct,
        })
        return analysis

    def _record_audit(self, action: str, target: str, details: Dict[str, Any]) -> None:
        self._audit_log.append({
            "action": action,
            "target": target,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": details,
        })

    def get_audit_log(self) -> List[Dict[str, Any]]:
        return list(self._audit_log)
