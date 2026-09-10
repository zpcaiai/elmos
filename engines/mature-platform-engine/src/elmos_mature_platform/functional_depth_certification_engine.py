from typing import Dict, List
from datetime import datetime, timezone

from elmos_mature_platform.types import (
    FunctionalArea,
    DepthLevel,
    FunctionalRequirement,
    DepthCertification,
    DepthGap
)

class FunctionalDepthCertificationEngine:
    """
    Engine to evaluate and certify functional depth of different areas.
    """
    
    def __init__(self):
        self.requirements: Dict[str, FunctionalRequirement] = {}
        self.certifications: Dict[str, DepthCertification] = {}
        
        self._depth_order = {
            DepthLevel.BASIC: 1,
            DepthLevel.STANDARD: 2,
            DepthLevel.ADVANCED: 3,
            DepthLevel.COMPLETE: 4
        }
        
        self._effort_estimates = {
            DepthLevel.BASIC: 8.0,
            DepthLevel.STANDARD: 16.0,
            DepthLevel.ADVANCED: 32.0,
            DepthLevel.COMPLETE: 48.0
        }
    
    def add_requirement(self, req: FunctionalRequirement) -> None:
        """Add or update a functional requirement."""
        self.requirements[req.req_id] = req
        
    def record_test_results(self, req_id: str, test_count: int, pass_count: int) -> None:
        """Record test results for a requirement."""
        if req_id not in self.requirements:
            raise ValueError(f"Requirement {req_id} not found.")
        req = self.requirements[req_id]
        req.test_count = test_count
        req.pass_count = pass_count
        
        if test_count > 0 and test_count == pass_count:
            req.certified = True
        else:
            req.certified = False
            
    def mark_implemented(self, req_id: str) -> None:
        """Mark a requirement as implemented."""
        if req_id not in self.requirements:
            raise ValueError(f"Requirement {req_id} not found.")
        self.requirements[req_id].implemented = True
        
    def create_certification(self, cert: DepthCertification) -> str:
        """Create a new depth certification."""
        self.certifications[cert.cert_id] = cert
        return cert.cert_id
        
    def _is_requirement_met(self, req: FunctionalRequirement) -> bool:
        return req.implemented and req.certified
        
    def evaluate_depth(self, cert_id: str) -> DepthCertification:
        """Evaluate achieved depth based on requirements for the given certification."""
        if cert_id not in self.certifications:
            raise ValueError(f"Certification {cert_id} not found.")
            
        cert = self.certifications[cert_id]
        area = cert.area
        
        area_reqs = [r for r in self.requirements.values() if r.area == area]
        
        cert.requirements_total = len(area_reqs)
        cert.requirements_met = sum(1 for r in area_reqs if self._is_requirement_met(r))
        
        if cert.requirements_total > 0:
            cert.coverage_pct = (cert.requirements_met / cert.requirements_total) * 100
        else:
            cert.coverage_pct = 0.0
            
        achieved = None
        for depth in [DepthLevel.BASIC, DepthLevel.STANDARD, DepthLevel.ADVANCED, DepthLevel.COMPLETE]:
            target_val = self._depth_order[depth]
            reqs_to_check = [r for r in area_reqs if self._depth_order[r.depth] <= target_val]
            
            reqs_at_depth = [r for r in area_reqs if r.depth == depth]
            if not reqs_at_depth:
                break
                
            all_met = all(self._is_requirement_met(r) for r in reqs_to_check)
            if all_met:
                achieved = depth
            else:
                break
                
        if achieved:
            cert.achieved_depth = achieved
        else:
            cert.achieved_depth = DepthLevel.BASIC
            
        return cert
        
    def certify_area(self, cert_id: str, certifier: str) -> DepthCertification:
        """Certify if all requirements up to target_depth are met."""
        cert = self.evaluate_depth(cert_id)
        target_val = self._depth_order[cert.target_depth]
        
        area_reqs = [r for r in self.requirements.values() if r.area == cert.area]
        basic_reqs = [r for r in area_reqs if self._depth_order[r.depth] <= self._depth_order[DepthLevel.BASIC]]
        basic_met = all(self._is_requirement_met(r) for r in basic_reqs) if basic_reqs else False
        
        if not basic_met and target_val >= self._depth_order[DepthLevel.BASIC]:
            achieved_val = 0
        else:
            achieved_val = self._depth_order[cert.achieved_depth]
            
        if achieved_val >= target_val:
            cert.certified = True
            cert.certified_at = datetime.now(timezone.utc).isoformat()
            cert.certifier = certifier
        else:
            cert.certified = False
            cert.certified_at = ""
            cert.certifier = ""
            
        return cert
        
    def get_depth_gaps(self, cert_id: str) -> List[DepthGap]:
        """Identify gaps between target and achieved depth."""
        cert = self.evaluate_depth(cert_id)
        
        gaps = []
        target_val = self._depth_order[cert.target_depth]
        area_reqs = [r for r in self.requirements.values() if r.area == cert.area]
        
        missing = []
        effort = 0.0
        
        for r in area_reqs:
            if self._depth_order[r.depth] <= target_val:
                if not self._is_requirement_met(r):
                    missing.append(r.req_id)
                    effort += self._effort_estimates[r.depth]
                    
        if missing:
            gaps.append(DepthGap(
                area=cert.area,
                target_depth=cert.target_depth,
                current_depth=cert.achieved_depth,
                missing_requirements=missing,
                effort_estimate_hours=effort
            ))
            
        return gaps
        
    def get_area_coverage(self, area: FunctionalArea) -> Dict:
        """Coverage report for area."""
        area_reqs = [r for r in self.requirements.values() if r.area == area]
        total = len(area_reqs)
        met = sum(1 for r in area_reqs if self._is_requirement_met(r))
        
        by_depth = {}
        for d in DepthLevel:
            d_reqs = [r for r in area_reqs if r.depth == d]
            d_total = len(d_reqs)
            d_met = sum(1 for r in d_reqs if self._is_requirement_met(r))
            by_depth[d.value] = {
                "total": d_total,
                "met": d_met,
                "coverage": (d_met / d_total * 100) if d_total > 0 else 0.0
            }
            
        return {
            "area": area.value,
            "total_requirements": total,
            "met_requirements": met,
            "overall_coverage": (met / total * 100) if total > 0 else 0.0,
            "by_depth": by_depth
        }
        
    def get_requirements_by_depth(self, depth: DepthLevel) -> List[FunctionalRequirement]:
        """Filter requirements by depth."""
        return [r for r in self.requirements.values() if r.depth == depth]
        
    def get_certification_report(self) -> Dict:
        """Summary: areas, depths, coverage, gaps"""
        report = {
            "total_certifications": len(self.certifications),
            "certified_count": sum(1 for c in self.certifications.values() if c.certified),
            "certifications": [],
            "overall_coverage": 0.0
        }
        
        total_reqs = 0
        total_met = 0
        
        for c in self.certifications.values():
            self.evaluate_depth(c.cert_id)
            gaps = self.get_depth_gaps(c.cert_id)
            
            c_dict = {
                "cert_id": c.cert_id,
                "area": c.area.value,
                "target_depth": c.target_depth.value,
                "achieved_depth": c.achieved_depth.value,
                "certified": c.certified,
                "coverage_pct": c.coverage_pct,
                "gaps": len(gaps[0].missing_requirements) if gaps else 0
            }
            report["certifications"].append(c_dict)
            
            total_reqs += c.requirements_total
            total_met += c.requirements_met
            
        if total_reqs > 0:
            report["overall_coverage"] = (total_met / total_reqs) * 100
            
        return report
        
    def estimate_effort_to_depth(self, area: FunctionalArea, target: DepthLevel) -> float:
        """Estimate hours to reach target depth for an area."""
        area_reqs = [r for r in self.requirements.values() if r.area == area]
        target_val = self._depth_order[target]
        
        effort = 0.0
        for r in area_reqs:
            if self._depth_order[r.depth] <= target_val:
                if not self._is_requirement_met(r):
                    effort += self._effort_estimates[r.depth]
                    
        return effort
