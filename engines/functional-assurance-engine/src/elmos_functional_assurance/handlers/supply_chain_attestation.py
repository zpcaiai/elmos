"""Supply Chain Security, SLSA Provenance, and Vulnerability VEX Governance."""

from __future__ import annotations

import hashlib
import time
from typing import Any, Mapping

from ..domain import ConformityDecision, FunctionalAssuranceContext


class SupplyChainAttestationCertifier:
    """Certifier for supply chain provenance, hermetic builds, SBOM, and VEX governance."""

    @staticmethod
    def verify_hermetic_build(
        context: FunctionalAssuranceContext,
        slsa_level: str = "SLSA_BUILD_LEVEL_3",
        builder_id: str = "https://github.com/slsa-framework/slsa-github-generator/.github/workflows/generator_generic_slsa3.yml",
        unpinned_dependencies_count: int = 0,
        network_isolation_enforced: bool = True,
    ) -> dict[str, Any]:
        passed = unpinned_dependencies_count == 0 and network_isolation_enforced
        return {
            "skill": "elmos-hermetic-build-environment-attestation-controller",
            "slsa_level": slsa_level,
            "builder_id": builder_id,
            "hermetic_build": network_isolation_enforced,
            "unpinned_dependencies": unpinned_dependencies_count,
            "decision": (ConformityDecision.CONFORMING if passed else ConformityDecision.NON_CONFORMING).value,
        }

    @staticmethod
    def audit_license_and_ip(
        context: FunctionalAssuranceContext,
        sbom_components: list[Mapping[str, Any]],
        prohibited_licenses: list[str] | None = None,
    ) -> dict[str, Any]:
        disallowed = set(prohibited_licenses or ["GPL-3.0", "AGPL-3.0", "SSPL-1.0", "UNKNOWN"])
        violations = []
        for comp in sbom_components:
            lic = str(comp.get("license", "UNKNOWN"))
            if lic in disallowed:
                violations.append({"component": comp.get("name"), "license": lic})

        clean = len(violations) == 0
        return {
            "skill": "elmos-open-source-license-ip-compliance-certifier",
            "components_scanned": len(sbom_components),
            "license_violations": violations,
            "ip_clean": clean,
            "decision": (ConformityDecision.CONFORMING if clean else ConformityDecision.NON_CONFORMING).value,
        }

    @staticmethod
    def govern_vulnerability_vex(
        context: FunctionalAssuranceContext,
        cve_findings: list[Mapping[str, Any]],
        cisa_kev_matches: int = 0,
    ) -> dict[str, Any]:
        unaddressed_criticals = [f for f in cve_findings if f.get("severity") == "CRITICAL" and not f.get("vex_justification")]
        passed = len(unaddressed_criticals) == 0 and cisa_kev_matches == 0
        return {
            "skill": "elmos-vulnerability-vex-kev-response-governor",
            "standard": "OpenVEX / CISA KEV / NIST NVD",
            "total_cves_reviewed": len(cve_findings),
            "unjustified_criticals": len(unaddressed_criticals),
            "cisa_kev_zero_tolerance_met": cisa_kev_matches == 0,
            "decision": (ConformityDecision.CONFORMING if passed else ConformityDecision.NON_CONFORMING).value,
        }
