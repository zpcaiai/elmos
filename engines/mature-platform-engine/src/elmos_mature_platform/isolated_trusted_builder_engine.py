from typing import Dict, List, Optional, Any
from datetime import datetime, timezone, timedelta

from elmos_mature_platform.types import (
    BuildRequest, BuildAttestation, BuildPolicy, BuildIsolationLevel,
    BuildVerdict, SlsaLevel
)

class IsolatedTrustedBuilderEngine:
    def __init__(self):
        self.requests: Dict[str, BuildRequest] = {}
        self.attestations: Dict[str, BuildAttestation] = {}
        self.policy: Optional[BuildPolicy] = None
        self._time_offset = timedelta(seconds=0)

    def _now(self) -> datetime:
        return datetime.now(timezone.utc) + self._time_offset
        
    def advance_time(self, seconds: int):
        self._time_offset += timedelta(seconds=seconds)

    def submit_build(self, request: BuildRequest) -> str:
        """Submit build request, return build_id"""
        self.requests[request.build_id] = request
        
        # Create an initial attestation with started_at
        self.attestations[request.build_id] = BuildAttestation(
            build_id=request.build_id,
            verdict=BuildVerdict.FAILED,  # placeholder
            started_at=self._now().isoformat()
        )
        return request.build_id

    def complete_build(self, build_id: str, artifact_digest: str, builder_digest: str, log_digest: str, network_accessed: bool, reproducible: bool) -> BuildAttestation:
        """Complete build with attestation data, compute SLSA level and verdict"""
        if build_id not in self.requests:
            raise ValueError(f"Unknown build_id {build_id}")
            
        req = self.requests[build_id]
        att = self.attestations[build_id]
        
        att.completed_at = self._now().isoformat()
        att.artifact_digest = artifact_digest
        att.builder_digest = builder_digest
        att.log_digest = log_digest
        att.network_accessed = network_accessed
        att.reproducible = reproducible
        
        # Compute duration
        started = datetime.fromisoformat(att.started_at)
        completed = datetime.fromisoformat(att.completed_at)
        duration = (completed - started).total_seconds()
        
        # Determine verdict
        if duration > req.timeout_seconds:
            att.verdict = BuildVerdict.TIMEOUT
        elif network_accessed and req.isolation_level in (BuildIsolationLevel.HERMETIC, BuildIsolationLevel.AIR_GAPPED):
            att.verdict = BuildVerdict.TAINTED
        elif not req.network_allowed and network_accessed:
             att.verdict = BuildVerdict.TAINTED
        else:
            att.verdict = BuildVerdict.PASSED

        # Compute SLSA level
        att.slsa_level = self.compute_slsa_level(build_id)
        return att

    def sign_provenance(self, build_id: str, signer_id: str) -> BuildAttestation:
        """Sign build provenance"""
        if build_id not in self.attestations:
            raise ValueError(f"Unknown build_id {build_id}")
        
        att = self.attestations[build_id]
        if att.verdict in (BuildVerdict.FAILED, BuildVerdict.TAINTED, BuildVerdict.TIMEOUT):
            raise ValueError("Cannot sign provenance for failed/tainted/timeout builds")
            
        att.provenance_signed = True
        att.slsa_level = self.compute_slsa_level(build_id)
        return att

    def verify_build(self, build_id: str) -> Dict[str, Any]:
        """Verify build integrity: check attestation, artifact digest, builder digest, SLSA level"""
        if build_id not in self.attestations:
            raise ValueError(f"Unknown build_id {build_id}")
            
        att = self.attestations[build_id]
        
        return {
            "build_id": build_id,
            "verdict": att.verdict.value,
            "slsa_level": att.slsa_level.value,
            "integrity_passed": att.verdict == BuildVerdict.PASSED,
            "artifact_digest_present": bool(att.artifact_digest),
            "builder_digest_present": bool(att.builder_digest),
            "provenance_signed": att.provenance_signed
        }

    def set_policy(self, policy: BuildPolicy):
        """Set build policy"""
        self.policy = policy

    def evaluate_policy(self, build_id: str) -> Dict[str, Any]:
        """Check build against policy"""
        if not self.policy:
            raise ValueError("No policy set")
            
        if build_id not in self.attestations:
            raise ValueError(f"Unknown build_id {build_id}")
            
        att = self.attestations[build_id]
        req = self.requests[build_id]
        policy = self.policy
        
        violations = []
        
        # Check isolation level (ordered: SHARED < TENANT_ISOLATED < HERMETIC < AIR_GAPPED)
        iso_levels = [BuildIsolationLevel.SHARED, BuildIsolationLevel.TENANT_ISOLATED, BuildIsolationLevel.HERMETIC, BuildIsolationLevel.AIR_GAPPED]
        req_iso_idx = iso_levels.index(req.isolation_level)
        pol_iso_idx = iso_levels.index(policy.min_isolation)
        if req_iso_idx < pol_iso_idx:
            violations.append(f"Isolation level {req.isolation_level.value} is lower than required {policy.min_isolation.value}")
            
        # Check SLSA level
        slsa_levels = [SlsaLevel.LEVEL_0, SlsaLevel.LEVEL_1, SlsaLevel.LEVEL_2, SlsaLevel.LEVEL_3, SlsaLevel.LEVEL_4]
        att_slsa_idx = slsa_levels.index(att.slsa_level)
        pol_slsa_idx = slsa_levels.index(policy.min_slsa_level)
        if att_slsa_idx < pol_slsa_idx:
            violations.append(f"SLSA level {att.slsa_level.value} is lower than required {policy.min_slsa_level.value}")
            
        if policy.require_reproducible and not att.reproducible:
            violations.append("Build is not reproducible")
            
        if policy.require_signed_provenance and not att.provenance_signed:
            violations.append("Build provenance is not signed")
            
        if policy.allowed_builder_digests and att.builder_digest not in policy.allowed_builder_digests:
            violations.append(f"Builder digest {att.builder_digest} not in allowed list")
            
        started = datetime.fromisoformat(att.started_at)
        completed = datetime.fromisoformat(att.completed_at)
        duration = (completed - started).total_seconds()
        if duration > policy.max_build_duration_seconds:
            violations.append("Build duration exceeded policy max duration")

        return {
            "build_id": build_id,
            "compliant": len(violations) == 0,
            "violations": violations
        }

    def get_build(self, build_id: str) -> BuildAttestation:
        """Get build attestation"""
        if build_id not in self.attestations:
            raise ValueError(f"Unknown build_id {build_id}")
        return self.attestations[build_id]

    def list_builds(self, tenant_id: Optional[str] = None, verdict: Optional[BuildVerdict] = None) -> List[BuildAttestation]:
        """List builds with optional filters"""
        res = []
        for b_id, att in self.attestations.items():
            req = self.requests[b_id]
            if tenant_id and req.tenant_id != tenant_id:
                continue
            if verdict and att.verdict != verdict:
                continue
            res.append(att)
        return res

    def compute_slsa_level(self, build_id: str) -> SlsaLevel:
        """Compute SLSA level"""
        att = self.attestations[build_id]
        req = self.requests[build_id]
        
        if att.verdict not in (BuildVerdict.PASSED, BuildVerdict.TAINTED):
            return SlsaLevel.LEVEL_0
            
        if not att.provenance_signed:
            return SlsaLevel.LEVEL_1
            
        is_hardened = req.isolation_level in (BuildIsolationLevel.TENANT_ISOLATED, BuildIsolationLevel.HERMETIC, BuildIsolationLevel.AIR_GAPPED)
        is_hermetic_or_air = req.isolation_level in (BuildIsolationLevel.HERMETIC, BuildIsolationLevel.AIR_GAPPED)
        
        if is_hermetic_or_air and att.reproducible and att.provenance_signed:
            return SlsaLevel.LEVEL_4
            
        if is_hardened and att.provenance_signed:
            return SlsaLevel.LEVEL_3
            
        if att.provenance_signed:
            return SlsaLevel.LEVEL_2
            
        return SlsaLevel.LEVEL_0

    def detect_tainted_builds(self) -> List[BuildAttestation]:
        """Find builds that accessed network in hermetic mode or had builder digest mismatch"""
        res = []
        for b_id, att in self.attestations.items():
            req = self.requests[b_id]
            
            tainted = False
            if att.network_accessed and req.isolation_level in (BuildIsolationLevel.HERMETIC, BuildIsolationLevel.AIR_GAPPED):
                tainted = True
            elif not req.network_allowed and att.network_accessed:
                tainted = True
            
            if self.policy and self.policy.allowed_builder_digests and att.builder_digest not in self.policy.allowed_builder_digests:
                tainted = True
                
            if tainted or att.verdict == BuildVerdict.TAINTED:
                # If we detect it dynamically here, we update the verdict
                att.verdict = BuildVerdict.TAINTED
                res.append(att)
        return res

    def get_supply_chain_report(self) -> Dict[str, Any]:
        """Summary: builds by verdict, by SLSA level, tainted count, policy violations"""
        verdict_counts = {}
        slsa_counts = {}
        tainted_count = len(self.detect_tainted_builds())
        policy_violations_count = 0
        
        for b_id, att in self.attestations.items():
            v = att.verdict.value
            verdict_counts[v] = verdict_counts.get(v, 0) + 1
            
            s = att.slsa_level.value
            slsa_counts[s] = slsa_counts.get(s, 0) + 1
            
            if self.policy:
                try:
                    res = self.evaluate_policy(b_id)
                    if not res["compliant"]:
                        policy_violations_count += 1
                except:
                    pass
                    
        return {
            "total_builds": len(self.attestations),
            "verdict_counts": verdict_counts,
            "slsa_counts": slsa_counts,
            "tainted_count": tainted_count,
            "policy_violations": policy_violations_count
        }
