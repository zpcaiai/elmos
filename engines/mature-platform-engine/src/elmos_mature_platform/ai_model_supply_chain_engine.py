import datetime
from typing import Dict, List, Optional, Set
from elmos_mature_platform.types import (
    AiModelRecord, ModelScanResult, ModelProvenance, ModelRiskLevel
)

class AiModelSupplyChainEngine:
    """
    Engine for managing AI model supply chain security.
    """

    def __init__(self):
        self.models: Dict[str, AiModelRecord] = {}
        self.scans: Dict[str, List[ModelScanResult]] = {}
        self.dependents: Dict[str, Set[str]] = {}  # model_id -> set of models that depend on it

    def _update_dependents(self, model: AiModelRecord):
        for dep in model.dependencies:
            if dep not in self.dependents:
                self.dependents[dep] = set()
            self.dependents[dep].add(model.model_id)

    def register_model(self, model: AiModelRecord) -> str:
        """Register model in registry"""
        if model.model_id in self.models:
            raise ValueError(f"Model {model.model_id} already registered.")
        if not model.registered_at:
            model.registered_at = datetime.datetime.now().isoformat()
        
        # Verify dependencies exist
        for dep in model.dependencies:
            if dep not in self.models:
                raise ValueError(f"Dependency {dep} not found.")

        # Check circular dependencies
        self._check_circular(model.model_id, model.dependencies)

        self.models[model.model_id] = model
        self.scans[model.model_id] = []
        self._update_dependents(model)
        return model.model_id

    def _check_circular(self, target_id: str, deps: List[str]):
        visited = set()
        
        def dfs(current: str):
            if current == target_id:
                raise ValueError(f"Circular dependency detected for {target_id}")
            if current in visited:
                return
            visited.add(current)
            if current in self.models:
                for d in self.models[current].dependencies:
                    dfs(d)
                    
        for d in deps:
            dfs(d)

    def scan_model(self, scan: ModelScanResult) -> str:
        """Record scan result"""
        if scan.model_id not in self.models:
            raise ValueError(f"Model {scan.model_id} not found.")
        if not scan.scanned_at:
            scan.scanned_at = datetime.datetime.now().isoformat()
        self.scans[scan.model_id].append(scan)
        return scan.scan_id

    def assess_risk(self, model_id: str) -> ModelRiskLevel:
        """Auto-assess risk"""
        if model_id not in self.models:
            raise ValueError(f"Model {model_id} not found.")
        
        model = self.models[model_id]
        
        base_risk = 0  # 0: LOW, 1: MEDIUM, 2: HIGH, 3: CRITICAL
        
        if model.provenance == ModelProvenance.UNKNOWN:
            base_risk = max(base_risk, 2)
            
        if not model.training_data_hash:
            base_risk = max(base_risk, 1)
            
        failed_scans = [s for s in self.scans.get(model_id, []) if not s.passed]
        if len(failed_scans) > 0:
            base_risk = min(3, base_risk + len(failed_scans))
            
        # Inherit vulnerabilities
        deps_vulns = self.get_vulnerability_report(model_id)
        total_vulns = len(deps_vulns["inherited_vulnerabilities"]) + len(deps_vulns["direct_vulnerabilities"])
        if total_vulns > 0:
            base_risk = min(3, base_risk + 1)
        if total_vulns >= 3:
            base_risk = min(3, base_risk + 2)

        risk_map = {
            0: ModelRiskLevel.LOW,
            1: ModelRiskLevel.MEDIUM,
            2: ModelRiskLevel.HIGH,
            3: ModelRiskLevel.CRITICAL
        }
        
        model.risk_level = risk_map[base_risk]
        return model.risk_level

    def approve_model(self, model_id: str, approver: str) -> AiModelRecord:
        """Must pass all scans, risk != CRITICAL"""
        if model_id not in self.models:
            raise ValueError(f"Model {model_id} not found.")
        
        model = self.models[model_id]
        
        # Check scans
        scans = self.scans.get(model_id, [])
        if not scans:
            raise ValueError(f"Model {model_id} has no scans.")
        for s in scans:
            if not s.passed:
                raise ValueError(f"Model {model_id} has failed scans.")
                
        # Re-assess risk just in case
        self.assess_risk(model_id)
        if model.risk_level == ModelRiskLevel.CRITICAL:
            raise ValueError(f"Cannot approve CRITICAL risk model.")
            
        model.approved = True
        model.approved_by = approver
        return model

    def revoke_approval(self, model_id: str, reason: str) -> AiModelRecord:
        """Revoke approval"""
        if model_id not in self.models:
            raise ValueError(f"Model {model_id} not found.")
        model = self.models[model_id]
        model.approved = False
        model.approved_by = ""
        return model

    def check_dependencies(self, model_id: str) -> Dict:
        """Check all deps approved, no circular deps"""
        if model_id not in self.models:
            raise ValueError(f"Model {model_id} not found.")
            
        model = self.models[model_id]
        unapproved = []
        for dep in model.dependencies:
            if dep in self.models and not self.models[dep].approved:
                unapproved.append(dep)
                
        return {
            "all_approved": len(unapproved) == 0,
            "unapproved_dependencies": unapproved
        }

    def get_vulnerability_report(self, model_id: str) -> Dict:
        """Model's vulns + inherited from deps"""
        if model_id not in self.models:
            raise ValueError(f"Model {model_id} not found.")
            
        model = self.models[model_id]
        inherited = []
        
        def collect_vulns(current: str, path: List[str]):
            if current in self.models:
                m = self.models[current]
                for v in m.vulnerabilities:
                    inherited.append({
                        "vulnerability": v,
                        "source_model": current,
                        "path": path + [current]
                    })
                for d in m.dependencies:
                    collect_vulns(d, path + [current])
                    
        for dep in model.dependencies:
            collect_vulns(dep, [])
            
        return {
            "model_id": model_id,
            "direct_vulnerabilities": list(model.vulnerabilities),
            "inherited_vulnerabilities": inherited
        }

    def get_model_lineage(self, model_id: str) -> Dict:
        """Full dependency tree"""
        if model_id not in self.models:
            raise ValueError(f"Model {model_id} not found.")
            
        def build_tree(current: str) -> Dict:
            if current not in self.models:
                return {"model_id": current, "status": "not_found", "dependencies": {}}
            m = self.models[current]
            return {
                "model_id": m.model_id,
                "approved": m.approved,
                "risk_level": m.risk_level.value,
                "dependencies": {d: build_tree(d) for d in m.dependencies}
            }
            
        return build_tree(model_id)

    def get_unapproved_models(self) -> List[AiModelRecord]:
        """Models not yet approved"""
        return [m for m in self.models.values() if not m.approved]

    def get_supply_chain_report(self) -> Dict:
        """By provenance, by risk, approved%, scan coverage"""
        total = len(self.models)
        if total == 0:
            return {}
            
        by_provenance = {}
        by_risk = {}
        approved_count = 0
        scan_coverage_count = 0
        
        for m in self.models.values():
            by_provenance[m.provenance.value] = by_provenance.get(m.provenance.value, 0) + 1
            by_risk[m.risk_level.value] = by_risk.get(m.risk_level.value, 0) + 1
            if m.approved:
                approved_count += 1
            if len(self.scans.get(m.model_id, [])) > 0:
                scan_coverage_count += 1
                
        return {
            "total_models": total,
            "by_provenance": by_provenance,
            "by_risk": by_risk,
            "approval_percentage": (approved_count / total) * 100,
            "scan_coverage_percentage": (scan_coverage_count / total) * 100
        }

    def quarantine_model(self, model_id: str, reason: str) -> AiModelRecord:
        """Mark as CRITICAL risk, revoke approval, cascade to dependent models"""
        if model_id not in self.models:
            raise ValueError(f"Model {model_id} not found.")
            
        visited = set()
        
        def apply_quarantine(current_id: str):
            if current_id in visited:
                return
            visited.add(current_id)
            m = self.models[current_id]
            m.risk_level = ModelRiskLevel.CRITICAL
            m.approved = False
            m.approved_by = ""
            if current_id in self.dependents:
                for dep in self.dependents[current_id]:
                    apply_quarantine(dep)
                    
        apply_quarantine(model_id)
        return self.models[model_id]
