"""K6: Security & Governance Kernel for Elmos Commercial Capability Expansion."""

from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any, Dict, List, Optional, Set

from ..models import (
    DecisionStatus,
    PolicyDecision,
    ProvenanceAttestation,
    TaskContext,
)


class SecurityGovernanceKernel:
    """Enforces policy-as-code, authorization, secret sanitization, SBOM, and SLSA provenance."""

    def __init__(self):
        self.policy_rules: List[Dict[str, Any]] = []
        self.secret_patterns: List[re.Pattern] = [
            re.compile(r"(?i)api[_-]?key\s*[:=]\s*['\"]?([a-zA-Z0-9_\-]{16,})['\"]?"),
            re.compile(r"(?i)secret\s*[:=]\s*['\"]?([a-zA-Z0-9_\-]{16,})['\"]?"),
            re.compile(r"(?i)password\s*[:=]\s*['\"]?([a-zA-Z0-9_\-]{8,})['\"]?"),
            re.compile(r"(?i)bearer\s+([a-zA-Z0-9_\-\.]{20,})"),
            re.compile(r"(?i)ghp_[a-zA-Z0-9]{36}"),
        ]
        self._load_default_policies()

    def _load_default_policies(self) -> None:
        self.policy_rules = [
            {
                "rule_id": "SEC-001",
                "name": "Deny arbitrary shell command execution",
                "action": "EXEC_UNRESTRICTED_SHELL",
                "effect": "DENY",
            },
            {
                "rule_id": "SEC-002",
                "name": "Require hermetic sandbox for untrusted code execution",
                "action": "EXEC_UNTRUSTED_CODE",
                "obligation": "SANDBOX_HERMETIC_ISOLATION",
                "effect": "ALLOW_WITH_OBLIGATION",
            },
            {
                "rule_id": "SEC-003",
                "name": "Prevent secret credential egress in logs and outputs",
                "action": "EXPORT_LOGS_OR_ARTIFACTS",
                "obligation": "REDACT_SECRETS",
                "effect": "ALLOW_WITH_OBLIGATION",
            },
            {
                "rule_id": "SEC-004",
                "name": "Deny cross-tenant storage or cache access",
                "action": "ACCESS_CROSS_TENANT_DATA",
                "effect": "DENY",
            },
        ]

    def evaluate_policy(
        self,
        principal: str,
        action: str,
        resource: str,
        context: TaskContext,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> PolicyDecision:
        """Evaluates policy-as-code rules for the requested action."""
        params = parameters or {}
        violations = []
        obligations = []
        allowed = True

        for r in self.policy_rules:
            if r.get("action") == action:
                effect = r.get("effect")
                if effect == "DENY":
                    allowed = False
                    violations.append(f"Policy violation [{r['rule_id']}]: {r['name']}")
                elif effect == "ALLOW_WITH_OBLIGATION":
                    obligations.append(r.get("obligation", ""))

        status = DecisionStatus.APPROVED if allowed else DecisionStatus.DENIED
        dec_id = f"pol-{hashlib.sha256((principal+action+resource).encode('utf-8')).hexdigest()[:10]}"

        return PolicyDecision(
            decision_id=dec_id,
            principal=principal,
            action=action,
            resource=resource,
            allowed=allowed,
            status=status,
            obligations=obligations,
            violations=violations,
        )

    def sanitize_secrets(self, text: str) -> tuple[str, int]:
        """Scans and redacts detected secrets, tokens, and credentials from text."""
        sanitized = text
        replacements = 0
        for pat in self.secret_patterns:
            matches = pat.findall(sanitized)
            for m in matches:
                sanitized = sanitized.replace(m, "[REDACTED_SECRET]")
                replacements += 1
        return sanitized, replacements

    def generate_slsa_provenance(
        self,
        subject_name: str,
        subject_digest: str,
        materials: List[Dict[str, str]],
        invocation_params: Dict[str, Any],
        signing_key: str = "elmos-internal-signing-key",
    ) -> ProvenanceAttestation:
        """Generates SLSA v1.0 provenance attestation with cryptographic signature."""
        att_id = f"slsa-{hashlib.sha256(subject_digest.encode('utf-8')).hexdigest()[:12]}"
        att = ProvenanceAttestation(
            attestation_id=att_id,
            subject_name=subject_name,
            subject_digest=subject_digest,
            predicate_type="https://slsa.dev/provenance/v1",
            builder_id="https://elmos.ai/builder/commercial-expansion@v2.0.0",
            invocation=invocation_params,
            materials=materials,
            slsa_level="SLSA_BUILD_LEVEL_3",
        )
        att.compute_signature(signing_key)
        return att

    def generate_cyclonedx_sbom(
        self,
        package_name: str,
        version: str,
        components: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        """Generates minimal CycloneDX format Software Bill of Materials (SBOM)."""
        return {
            "bomFormat": "CycloneDX",
            "specVersion": "1.5",
            "serialNumber": f"urn:uuid:{hashlib.sha256((package_name + version).encode('utf-8')).hexdigest()[:32]}",
            "version": 1,
            "metadata": {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "component": {
                    "type": "application",
                    "name": package_name,
                    "version": version,
                },
            },
            "components": [
                {
                    "type": "library",
                    "name": c.get("name"),
                    "version": c.get("version", "1.0.0"),
                    "purl": f"pkg:generic/{c.get('name')}@{c.get('version', '1.0.0')}",
                    "licenses": [{"license": {"id": c.get("license", "Apache-2.0")}}],
                }
                for c in components
            ],
        }
