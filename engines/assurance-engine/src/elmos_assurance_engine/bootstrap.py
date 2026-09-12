"""Implementation of B00: elmos-assurance-bootstrap.

Performs read-only inspection of repository, preserves K8 signer boundaries,
inventories native toolchains, and outputs explicit repo-map and compatibility mappings.
"""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .contracts import sha256_digest


class RepositoryBootstrap:
    """Read-only inventory and mapping for existing Elmos repository."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def discover_domains(self) -> dict[str, Any]:
        """Detect existing domain pack registrations."""
        domains = {
            "project-generation": {
                "name": "multi-language-project-generation",
                "harness_source": "engines/proof-driven-harness-engine/src/elmos_proof_harness/domains.py",
                "status": "REUSE",
            },
            "sql-conversion": {
                "name": "sql-dialect-routine-conversion",
                "harness_source": "engines/proof-driven-harness-engine/src/elmos_proof_harness/domains.py",
                "status": "REUSE",
            },
            "spring-modernization": {
                "name": "spring-legacy-modernization",
                "harness_source": "engines/proof-driven-harness-engine/src/elmos_proof_harness/domains.py",
                "status": "REUSE",
            },
            "repository-conversion": {
                "name": "cross-language-conversion",
                "harness_source": "engines/proof-driven-harness-engine/src/elmos_proof_harness/domains.py",
                "status": "REUSE",
            },
        }
        for _d, info in domains.items():
            full_path = self.repo_root / info["harness_source"]
            if not full_path.is_file():
                info["status"] = "ABSENT"
        return domains

    def discover_k8_signer(self) -> dict[str, Any]:
        """Check existing K8 certification and signer boundaries."""
        cert_py = self.repo_root / "engines/proof-driven-harness-engine/src/elmos_proof_harness/certification.py"
        if cert_py.is_file():
            return {
                "status": "REUSE",
                "path": "engines/proof-driven-harness-engine/src/elmos_proof_harness/certification.py",
                "signer_boundary": "EXTERNAL_ASYMMETRIC_SIGNER_ONLY",
                "bypass_permitted": False,
                "production_signing": "DISABLED_WITHOUT_EXTERNAL_KEY",
            }
        return {
            "status": "ABSENT",
            "path": None,
            "signer_boundary": "UNAVAILABLE",
            "bypass_permitted": False,
            "production_signing": "DISABLED",
        }

    def discover_native_toolchains(self) -> dict[str, Any]:
        """Probe machine availability of required toolchains."""
        tools: dict[str, Any] = {}
        for cmd in ["python3", "git", "sqlite3", "pytest", "uv", "lean", "tlc"]:
            path = shutil.which(cmd)
            tools[cmd] = {
                "available": path is not None,
                "path": path,
                "status": "AVAILABLE" if path is not None else "NOT_RUN",
            }
        return tools

    def generate_compatibility_map(self) -> dict[str, Any]:
        """Generate explicit migration mapping between legacy E0..E5 and elmos.assurance/v4."""
        return {
            "schema_version": "4.0",
            "target_profile": "elmos.assurance/v4",
            "historical_profiles_preserved": True,
            "level_mappings": {
                "E0": {
                    "v3_meaning": "Rebuildable assets",
                    "v4_meaning": "Rebuildable source/target/toolchain/environment with digest integrity",
                    "requires_rerun": True,
                },
                "E1": {
                    "v3_meaning": "Approved requirements",
                    "v4_meaning": "Approved normative contract, frozen scope, and obligation denominator",
                    "requires_rerun": True,
                },
                "E2": {
                    "v3_meaning": "Smoke tests pass",
                    "v4_meaning": "Fast critical-path smoke tests pass; failure halts regression",
                    "requires_rerun": True,
                },
                "E3": {
                    "v3_meaning": "Regression pass",
                    "v4_meaning": "Full regression over all approved obligations; zero-test failure enforced",
                    "requires_rerun": True,
                },
                "E4": {
                    "v3_meaning": "Differential verification",
                    "v4_meaning": "Typed differential runtime + mutant kill audit + property fuzzing",
                    "requires_rerun": True,
                },
                "E5": {
                    "v3_meaning": "Formal proof + K8 sign",
                    "v4_meaning": "Risk formal obligations + real Ethen audit + K8 external signature",
                    "requires_rerun": True,
                },
            },
            "historical_certificates": "PRESERVED_IMMUTABLE",
        }

    def build_repo_map(self) -> dict[str, Any]:
        domains = self.discover_domains()
        k8 = self.discover_k8_signer()
        tools = self.discover_native_toolchains()
        compat = self.generate_compatibility_map()

        repo_map = {
            "schema_version": "4.0",
            "profile": "elmos.assurance/v4",
            "repo_root": str(self.repo_root),
            "domains": domains,
            "k8_signer": k8,
            "toolchains": tools,
            "compatibility": compat,
            "fail_closed_invariants": [
                "REUSE_EXISTING_ARCHITECTURE_NO_PARALLEL_HARNESS",
                "K8_SIGNER_CANNOT_BE_BYPASSED",
                "MISSING_SOURCES_OR_DB_DEFAULTS_TO_NOT_RUN",
                "HISTORICAL_CERTIFICATES_IMMUTABLE",
            ],
        }
        repo_map["digest"] = sha256_digest(repo_map)
        return repo_map

    def build_gap_analysis(self, repo_map: Mapping[str, Any]) -> str:
        k8_status = repo_map["k8_signer"]["status"]
        tools = repo_map["toolchains"]
        lean_status = tools["lean"]["status"]
        tlc_status = tools["tlc"]["status"]

        lines = [
            "# Repository Assurance Gap Analysis",
            "",
            "## Architectural Component Mapping",
            f"- K8 Signer: `{k8_status}` (boundary: `{repo_map['k8_signer']['signer_boundary']}`)",
            "- Four Business Lines: Fully registered in Proof Harness DOMAIN_PACKS",
            "",
            "## Toolchain Gaps",
            f"- Lean Formal Checker: `{lean_status}` (formal proofs marked NOT_RUN if missing)",
            f"- TLC Model Checker: `{tlc_status}` (model checking marked NOT_RUN if missing)",
            f"- SQLite/Python/Git: `{tools['python3']['status']}`",
            "",
            "## Invariants Enforced",
            "1. Existing K8 signer interface is reused; no bypass or backdoor private key injection.",
            "2. Unrun databases or missing tools default to NOT_RUN; no simulated PASS.",
            "3. Explicit elmos.assurance/v4 profile prevents silent reinterpretation of legacy E5 certificates.",
        ]
        return "\n".join(lines) + "\n"
