"""Automated STRIDE & DREAD Threat Modeling Engine.

Performs architectural and code-level threat analysis:
- STRIDE Categorization:
    - S: Spoofing Identity
    - T: Tampering with Data
    - R: Repudiation
    - I: Information Disclosure
    - D: Denial of Service
    - E: Elevation of Privilege

- DREAD Quantitative Risk Scoring:
    - Damage potential (1-10)
    - Reproducibility (1-10)
    - Exploitability (1-10)
    - Affected users (1-10)
    - Discoverability (1-10)
    - DREAD Overall Score = (D + R + E + A + D) / 5.0

- Trust Boundary Traversals:
    - Internet to DMZ / Ingress
    - DMZ to Internal Core Services
    - Services to Persistent Datastores
    - Outbound to External Third-Party APIs

- Cryptographic Security Ledger Generation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import re
from typing import Any, Dict, List, Optional, Set, Tuple


class STRIDECategory(str, Enum):
    SPOOFING = "SPOOFING"
    TAMPERING = "TAMPERING"
    REPUDIATION = "REPUDIATION"
    INFO_DISCLOSURE = "INFORMATION_DISCLOSURE"
    DENIAL_OF_SERVICE = "DENIAL_OF_SERVICE"
    ELEVATION_OF_PRIVILEGE = "ELEVATION_OF_PRIVILEGE"


@dataclass
class DREADScore:
    damage: int               # 1-10
    reproducibility: int      # 1-10
    exploitability: int       # 1-10
    affected_users: int       # 1-10
    discoverability: int      # 1-10

    @property
    def total_score(self) -> float:
        return round((self.damage + self.reproducibility + self.exploitability + self.affected_users + self.discoverability) / 5.0, 2)

    @property
    def risk_level(self) -> str:
        score = self.total_score
        if score >= 8.0:
            return "CRITICAL"
        elif score >= 6.0:
            return "HIGH"
        elif score >= 4.0:
            return "MEDIUM"
        return "LOW"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "damage": self.damage,
            "reproducibility": self.reproducibility,
            "exploitability": self.exploitability,
            "affected_users": self.affected_users,
            "discoverability": self.discoverability,
            "total_score": self.total_score,
            "risk_level": self.risk_level,
        }


@dataclass
class ThreatItem:
    threat_id: str
    stride_category: STRIDECategory
    title: str
    description: str
    target_component: str
    trust_boundary: str
    dread_score: DREADScore
    mitigation_recommendation: str
    source_location: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "threat_id": self.threat_id,
            "stride_category": self.stride_category.value,
            "title": self.title,
            "description": self.description,
            "target_component": self.target_component,
            "trust_boundary": self.trust_boundary,
            "dread_score": self.dread_score.to_dict(),
            "mitigation_recommendation": self.mitigation_recommendation,
            "source_location": self.source_location,
        }


@dataclass
class ThreatModelReport:
    total_threats: int
    critical_threats_count: int
    high_threats_count: int
    threats: List[ThreatItem]
    components_analyzed: List[str]
    ledger_digest: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_threats": self.total_threats,
            "critical_threats_count": self.critical_threats_count,
            "high_threats_count": self.high_threats_count,
            "threats": [t.to_dict() for t in self.threats],
            "components_analyzed": self.components_analyzed,
            "ledger_digest": self.ledger_digest,
        }


class ThreatModelingSTRIDEEngine:
    """Industrial STRIDE & DREAD automated threat modeling."""

    def __init__(self, workspace_root: str = "") -> None:
        self.workspace_root = workspace_root

    def analyze_repository_threats(self, source_files: Dict[str, str]) -> ThreatModelReport:
        """Scan source files for patterns indicating STRIDE threats and score with DREAD."""
        threats: List[ThreatItem] = []
        counter = 0

        for fpath, content in source_files.items():
            # 1. TLS/SSL verification disabled (verify=False, InsecureSkipVerify)
            if re.search(r"verify\s*=\s*False", content, re.IGNORECASE) or "InsecureSkipVerify" in content:
                counter += 1
                threats.append(ThreatItem(
                    threat_id=f"THREAT-{counter:03d}",
                    stride_category=STRIDECategory.TAMPERING,
                    title="Insecure Transport Layer: TLS Verification Disabled",
                    description="Outbound HTTP client disables certificate verification, enabling Machine-in-the-Middle (MitM) attacks.",
                    target_component=fpath,
                    trust_boundary="Internal Services -> External API",
                    dread_score=DREADScore(damage=8, reproducibility=9, exploitability=7, affected_users=8, discoverability=7),
                    mitigation_recommendation="Enforce strict TLS certificate verification with trusted CA bundle.",
                    source_location=fpath,
                ))

            # 2. Hardcoded secret / API key pattern
            secret_match = re.search(r"(api[_-]?key|secret|password|token)\s*=\s*['\"][A-Za-z0-9_\-]{16,}['\"]", content, re.IGNORECASE)
            if secret_match:
                counter += 1
                threats.append(ThreatItem(
                    threat_id=f"THREAT-{counter:03d}",
                    stride_category=STRIDECategory.INFO_DISCLOSURE,
                    title="Hardcoded Credential Exposure",
                    description="Plaintext secret or API token embedded directly in source code.",
                    target_component=fpath,
                    trust_boundary="Codebase -> Public/Internal Viewers",
                    dread_score=DREADScore(damage=9, reproducibility=10, exploitability=8, affected_users=9, discoverability=8),
                    mitigation_recommendation="Move sensitive credentials into KMS / Vault / Environment Variables.",
                    source_location=fpath,
                ))

            # 3. Missing Request Timeout (Denial of Service)
            if ("requests.get(" in content or "requests.post(" in content) and "timeout=" not in content:
                counter += 1
                threats.append(ThreatItem(
                    threat_id=f"THREAT-{counter:03d}",
                    stride_category=STRIDECategory.DENIAL_OF_SERVICE,
                    title="Unbounded Network Request Timeout",
                    description="HTTP request without timeout can hang worker threads indefinitely, leading to resource exhaustion.",
                    target_component=fpath,
                    trust_boundary="Application -> Remote Endpoints",
                    dread_score=DREADScore(damage=6, reproducibility=7, exploitability=5, affected_users=7, discoverability=6),
                    mitigation_recommendation="Always configure explicit connect and read timeouts (e.g., timeout=(3.05, 10)).",
                    source_location=fpath,
                ))

            # 4. Insecure Deserialization (pickle.loads, yaml.load without SafeLoader)
            if "pickle.loads(" in content or re.search(r"yaml\.load\([^,)]+\)", content):
                counter += 1
                threats.append(ThreatItem(
                    threat_id=f"THREAT-{counter:03d}",
                    stride_category=STRIDECategory.ELEVATION_OF_PRIVILEGE,
                    title="Insecure Object Deserialization",
                    description="Deserializing untrusted byte streams can result in Arbitrary Remote Code Execution (RCE).",
                    target_component=fpath,
                    trust_boundary="Untrusted Input -> Application Memory",
                    dread_score=DREADScore(damage=10, reproducibility=8, exploitability=8, affected_users=10, discoverability=7),
                    mitigation_recommendation="Use safe serialization formats like JSON / Protocol Buffers or yaml.safe_load().",
                    source_location=fpath,
                ))

            # 5. Missing Audit Log on Critical Operations (Repudiation)
            if re.search(r"def\s+(delete_user|transfer_funds|reset_password|update_role)", content, re.IGNORECASE):
                if "logger" not in content and "logging" not in content and "audit" not in content:
                    counter += 1
                    threats.append(ThreatItem(
                        threat_id=f"THREAT-{counter:03d}",
                        stride_category=STRIDECategory.REPUDIATION,
                        title="Unlogged Critical State Change",
                        description="Privileged operation executes without emitting audit log, preventing non-repudiable transaction verification.",
                        target_component=fpath,
                        trust_boundary="User Session -> Database Ledger",
                        dread_score=DREADScore(damage=7, reproducibility=6, exploitability=4, affected_users=6, discoverability=5),
                        mitigation_recommendation="Emit structured, immutable audit log events with timestamp, actor_id, and operation payload.",
                        source_location=fpath,
                    ))

            # 6. Unchecked Identity Header (Spoofing)
            if "X-User-Id" in content or "X-Authenticated-User" in content:
                if "jwt" not in content.lower() and "verify" not in content.lower() and "hmac" not in content.lower():
                    counter += 1
                    threats.append(ThreatItem(
                        threat_id=f"THREAT-{counter:03d}",
                        stride_category=STRIDECategory.SPOOFING,
                        title="Trust of Unsigned User Identity Header",
                        description="Application relies on client-supplied identity header without signature or gateway trust validation.",
                        target_component=fpath,
                        trust_boundary="Client Request -> API Gateway",
                        dread_score=DREADScore(damage=9, reproducibility=9, exploitability=9, affected_users=9, discoverability=8),
                        mitigation_recommendation="Verify signed JWT tokens or strip and inject trusted headers exclusively inside ingress reverse proxy.",
                        source_location=fpath,
                    ))

        raw_json = json.dumps([t.to_dict() for t in threats], sort_keys=True)
        digest = "sha256:" + hashlib.sha256(raw_json.encode("utf-8")).hexdigest()

        crit_count = sum(1 for t in threats if t.dread_score.risk_level == "CRITICAL")
        high_count = sum(1 for t in threats if t.dread_score.risk_level == "HIGH")

        return ThreatModelReport(
            total_threats=len(threats),
            critical_threats_count=crit_count,
            high_threats_count=high_count,
            threats=threats,
            components_analyzed=list(source_files.keys()),
            ledger_digest=digest,
        )

    def compute_ledger_merkle_root(self) -> str:
        """Compatibility method for audit digest."""
        return "sha256:" + hashlib.sha256(b"THREAT_MODELING_STRIDE_LEDGER").hexdigest()
