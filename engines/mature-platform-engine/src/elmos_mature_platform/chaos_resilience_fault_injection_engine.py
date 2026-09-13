from typing import List, Dict, Optional
from datetime import datetime, timezone
import uuid

from elmos_mature_platform.physical.kubernetes_api import KubernetesControlPlaneDriver
from elmos_mature_platform.physical.toxiproxy import ToxiproxyDriver
from elmos_mature_platform.types import (
    FaultInjectionRule,
    ChaosExperiment,
    ExperimentStatus,
    ChaosFaultType as FaultType
)


class ChaosResilienceFaultInjectionEngine:
    """
    Engine for managing chaos resilience and fault injection experiments.
    """

    def __init__(
        self,
        toxiproxy_driver: Optional[ToxiproxyDriver] = None,
        kubernetes_driver: Optional[KubernetesControlPlaneDriver] = None,
    ):
        self._rules: Dict[str, FaultInjectionRule] = {}
        self._experiments: Dict[str, ChaosExperiment] = {}
        self._toxiproxy = toxiproxy_driver or ToxiproxyDriver.from_env()
        self._k8s = kubernetes_driver or KubernetesControlPlaneDriver.from_env()
        self._physical_receipts: List[Dict] = []
        self._experiment_proxies: Dict[str, List[str]] = {}

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def create_rule(self, rule: FaultInjectionRule) -> str:
        """Create a fault injection rule."""
        if not (0.0 <= rule.probability <= 1.0):
            raise ValueError("Probability must be between 0.0 and 1.0")
        
        # We allow overriding if rule_id already exists, or we just store it
        self._rules[rule.rule_id] = rule
        return rule.rule_id

    def create_experiment(self, experiment: ChaosExperiment) -> str:
        """Create a chaos experiment."""
        experiment.status = ExperimentStatus.DRAFT
        self._experiments[experiment.experiment_id] = experiment
        return experiment.experiment_id

    def add_rule_to_experiment(self, experiment_id: str, rule_id: str) -> None:
        """Link a rule to an experiment."""
        if experiment_id not in self._experiments:
            raise KeyError(f"Experiment {experiment_id} not found")
        if rule_id not in self._rules:
            raise KeyError(f"Rule {rule_id} not found")
        
        experiment = self._experiments[experiment_id]
        if experiment.status != ExperimentStatus.DRAFT:
            raise ValueError("Can only add rules to DRAFT experiments")
            
        if rule_id not in experiment.rules:
            experiment.rules.append(rule_id)

    def approve_experiment(self, experiment_id: str, approver: str) -> ChaosExperiment:
        """Approve a DRAFT experiment."""
        if experiment_id not in self._experiments:
            raise KeyError(f"Experiment {experiment_id} not found")
            
        experiment = self._experiments[experiment_id]
        if experiment.status != ExperimentStatus.DRAFT:
            raise ValueError("Experiment must be in DRAFT status to be approved")
            
        if experiment.blast_radius == "region" and not approver:
            # Enforce some logic for region blast radius requires explicit approval string
            raise PermissionError("Region blast radius requires explicit approval identity")
            
        if not approver:
            raise ValueError("Approver cannot be empty")

        experiment.status = ExperimentStatus.APPROVED
        experiment.approved_by = approver
        return experiment

    def start_experiment(self, experiment_id: str) -> ChaosExperiment:
        """Start an APPROVED experiment."""
        if experiment_id not in self._experiments:
            raise KeyError(f"Experiment {experiment_id} not found")
            
        experiment = self._experiments[experiment_id]
        if experiment.status != ExperimentStatus.APPROVED:
            raise ValueError("Experiment must be APPROVED to start")
            
        experiment.status = ExperimentStatus.RUNNING
        experiment.started_at = self._now_iso()
        proxy_names: List[str] = []
        for rule_id in experiment.rules:
            rule = self._rules.get(rule_id)
            if not rule:
                continue
            latency = None
            if rule.parameters.get("latency_ms"):
                try:
                    latency = int(rule.parameters["latency_ms"])
                except (TypeError, ValueError):
                    latency = None
            injection = self._toxiproxy.inject_fault(
                target_service=rule.target_service,
                fault_type=rule.fault_type.value,
                probability=rule.probability,
                latency_ms=latency,
            )
            self._physical_receipts.append(injection.to_dict())
            proxy_names.append(injection.proxy_name)
            chaos = self._k8s.apply_chaos_mesh(
                service_name=rule.target_service,
                fault_type=rule.fault_type.value,
                latency_ms=latency or 250,
            )
            self._physical_receipts.append(chaos.to_dict())
        self._experiment_proxies[experiment_id] = proxy_names
        return experiment

    def complete_experiment(self, experiment_id: str, summary: str, hypothesis_confirmed: bool) -> ChaosExperiment:
        """Complete a RUNNING experiment."""
        if experiment_id not in self._experiments:
            raise KeyError(f"Experiment {experiment_id} not found")
            
        experiment = self._experiments[experiment_id]
        if experiment.status != ExperimentStatus.RUNNING:
            raise ValueError("Experiment must be RUNNING to complete")
            
        experiment.status = ExperimentStatus.COMPLETED
        experiment.completed_at = self._now_iso()
        experiment.result_summary = summary
        experiment.hypothesis_confirmed = hypothesis_confirmed
        return experiment

    def abort_experiment(self, experiment_id: str, reason: str) -> ChaosExperiment:
        """Emergency abort of a RUNNING experiment."""
        if experiment_id not in self._experiments:
            raise KeyError(f"Experiment {experiment_id} not found")
            
        experiment = self._experiments[experiment_id]
        if experiment.status != ExperimentStatus.RUNNING:
            raise ValueError("Experiment must be RUNNING to abort")
            
        experiment.status = ExperimentStatus.ABORTED
        experiment.completed_at = self._now_iso()
        experiment.result_summary = f"ABORTED: {reason}"
        reset = self._toxiproxy.reset()
        self._physical_receipts.append(reset.to_dict())
        return experiment

    def rollback_experiment(self, experiment_id: str) -> ChaosExperiment:
        """Rollback an experiment from RUNNING, COMPLETED or ABORTED status."""
        if experiment_id not in self._experiments:
            raise KeyError(f"Experiment {experiment_id} not found")
            
        experiment = self._experiments[experiment_id]
        valid_rollback_statuses = [
            ExperimentStatus.RUNNING, 
            ExperimentStatus.COMPLETED, 
            ExperimentStatus.ABORTED
        ]
        
        if experiment.status not in valid_rollback_statuses:
            raise ValueError(f"Cannot rollback experiment in status {experiment.status}")
            
        experiment.status = ExperimentStatus.ROLLED_BACK
        experiment.completed_at = self._now_iso()
        # append rollback info to result summary
        experiment.result_summary += " | ROLLED_BACK"
        reset = self._toxiproxy.reset()
        self._physical_receipts.append(reset.to_dict())
        return experiment

    def get_active_experiments(self) -> List[ChaosExperiment]:
        """Get all RUNNING experiments."""
        return [
            exp for exp in self._experiments.values() 
            if exp.status == ExperimentStatus.RUNNING
        ]

    def get_blast_radius_assessment(self, experiment_id: str) -> Dict:
        """Get the blast radius assessment for an experiment."""
        if experiment_id not in self._experiments:
            raise KeyError(f"Experiment {experiment_id} not found")
            
        experiment = self._experiments[experiment_id]
        
        services_affected = set()
        total_duration = 0
        rule_details = []
        
        for rule_id in experiment.rules:
            rule = self._rules.get(rule_id)
            if rule:
                services_affected.add(rule.target_service)
                total_duration = max(total_duration, rule.duration_seconds)
                rule_details.append({
                    "rule_id": rule.rule_id,
                    "target": rule.target_service,
                    "type": rule.fault_type
                })
                
        return {
            "blast_radius": experiment.blast_radius,
            "services_affected": list(services_affected),
            "total_duration_seconds": total_duration,
            "rules": rule_details
        }

    def get_experiment_history(self, service: str) -> List[ChaosExperiment]:
        """Get all experiments targeting a specific service."""
        history = []
        for exp in self._experiments.values():
            targets = set()
            for rule_id in exp.rules:
                rule = self._rules.get(rule_id)
                if rule:
                    targets.add(rule.target_service)
            if service in targets:
                history.append(exp)
        return history

    def get_chaos_report(self) -> Dict:
        """Get a report of all chaos experiments."""
        total = len(self._experiments)
        by_status = {}
        for status in ExperimentStatus:
            by_status[status.value] = 0
            
        confirmed_count = 0
        completed_count = 0
        fault_counts = {}
        
        for exp in self._experiments.values():
            by_status[exp.status.value] += 1
            if exp.status == ExperimentStatus.COMPLETED:
                completed_count += 1
                if exp.hypothesis_confirmed:
                    confirmed_count += 1
                    
            for rule_id in exp.rules:
                rule = self._rules.get(rule_id)
                if rule:
                    fault_type = rule.fault_type.value
                    fault_counts[fault_type] = fault_counts.get(fault_type, 0) + 1
                    
        return {
            "total_experiments": total,
            "by_status": by_status,
            "hypothesis_confirmation_rate": (confirmed_count / completed_count) if completed_count > 0 else 0.0,
            "common_faults": fault_counts
        }
