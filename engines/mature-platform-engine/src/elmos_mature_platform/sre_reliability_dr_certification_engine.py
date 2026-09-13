import datetime
import uuid
from typing import Dict, List, Optional
from elmos_mature_platform.types import (
    ReliabilityDomain,
    CertificationLevel,
    ReliabilityMetric,
    ReliabilityCertification
)

class SreReliabilityDrCertificationEngine:
    """Engine for managing SRE Reliability and Disaster Recovery certification for services."""

    def __init__(self):
        self._metrics: Dict[str, ReliabilityMetric] = {}
        self._certifications: Dict[str, ReliabilityCertification] = {}

    def record_metric(self, metric: ReliabilityMetric) -> str:
        """Records a reliability metric and automatically checks if it is met."""
        if metric.domain == ReliabilityDomain.AVAILABILITY:
            metric.met = metric.actual_value >= metric.target_value
        elif metric.domain in [ReliabilityDomain.LATENCY, ReliabilityDomain.ERROR_RATE]:
            metric.met = metric.actual_value <= metric.target_value
        elif metric.domain == ReliabilityDomain.THROUGHPUT:
            metric.met = metric.actual_value >= metric.target_value
        else:
            # DR metrics (RTO/RPO), lower is better
            metric.met = metric.actual_value <= metric.target_value

        self._metrics[metric.metric_id] = metric
        return metric.metric_id

    def create_certification(self, cert: ReliabilityCertification) -> str:
        """Creates a new certification record."""
        self._certifications[cert.cert_id] = cert
        return cert.cert_id

    def add_metric_to_cert(self, cert_id: str, metric_id: str) -> ReliabilityCertification:
        """Links a metric to a certification."""
        if cert_id not in self._certifications:
            raise ValueError(f"Certification {cert_id} not found")
        if metric_id not in self._metrics:
            raise ValueError(f"Metric {metric_id} not found")
            
        cert = self._certifications[cert_id]
        if metric_id not in cert.metrics:
            cert.metrics.append(metric_id)
        
        return cert

    def evaluate_certification(self, cert_id: str) -> ReliabilityCertification:
        """Evaluates all metrics in the certification to check if met, updates gaps."""
        if cert_id not in self._certifications:
            raise ValueError(f"Certification {cert_id} not found")
            
        cert = self._certifications[cert_id]
        
        reqs = self.get_level_requirements(cert.level)
        avail_target = reqs["availability_target"]
        
        gaps = []
        all_met = True
        has_availability = False
        
        for mid in cert.metrics:
            m = self._metrics[mid]
            
            if m.domain == ReliabilityDomain.AVAILABILITY:
                has_availability = True
                if m.actual_value < avail_target:
                    gaps.append(f"Availability {m.actual_value}% is below {cert.level} target {avail_target}%")
                    all_met = False
            elif not m.met:
                gaps.append(f"Metric {m.name} not met (actual: {m.actual_value} vs target: {m.target_value})")
                all_met = False
                
        if not has_availability:
            gaps.append("Missing required AVAILABILITY metric")
            all_met = False
            
        cert.gaps = gaps
        return cert

    def certify(self, cert_id: str, certifier: str) -> ReliabilityCertification:
        """Certifies only if all metrics are met and gaps are empty after evaluation."""
        if cert_id not in self._certifications:
            raise ValueError(f"Certification {cert_id} not found")
            
        cert = self.evaluate_certification(cert_id)
        
        if len(cert.gaps) > 0:
            raise ValueError(f"Cannot certify {cert_id}. Existing gaps: {cert.gaps}")
            
        cert.certified = True
        cert.certifier = certifier
        cert.certified_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        return cert

    def get_level_requirements(self, level: CertificationLevel) -> Dict:
        """Returns the minimum requirements per certification level."""
        targets = {
            CertificationLevel.BRONZE: 99.0,
            CertificationLevel.SILVER: 99.9,
            CertificationLevel.GOLD: 99.95,
            CertificationLevel.PLATINUM: 99.99
        }
        return {
            "availability_target": targets.get(level, 99.0)
        }

    def get_service_reliability_score(self, service_name: str) -> float:
        """Returns the percentage of metrics met for all certifications of a service."""
        metrics_evaluated = 0
        metrics_met = 0
        
        for cert in self._certifications.values():
            if cert.service_name == service_name:
                for mid in cert.metrics:
                    metrics_evaluated += 1
                    if self._metrics[mid].met:
                        metrics_met += 1
                        
        if metrics_evaluated == 0:
            return 0.0
            
        return (metrics_met / metrics_evaluated) * 100.0

    def get_gaps(self, cert_id: str) -> List[str]:
        """Returns unmet metric descriptions / gaps for a certification."""
        cert = self.evaluate_certification(cert_id)
        return cert.gaps

    def get_certification_history(self, service_name: str) -> List[ReliabilityCertification]:
        """Returns all certifications for a service."""
        return [c for c in self._certifications.values() if c.service_name == service_name]

    def get_fleet_reliability_report(self) -> Dict:
        """Returns a report of all services, their cert levels, and metric compliance."""
        report = {}
        for cert in self._certifications.values():
            if cert.service_name not in report:
                report[cert.service_name] = {
                    "cert_levels": set(),
                    "certified": False,
                    "reliability_score": self.get_service_reliability_score(cert.service_name)
                }
            report[cert.service_name]["cert_levels"].add(cert.level.value)
            if cert.certified:
                report[cert.service_name]["certified"] = True
                
        for s in report:
            report[s]["cert_levels"] = list(report[s]["cert_levels"])
            
        return report
