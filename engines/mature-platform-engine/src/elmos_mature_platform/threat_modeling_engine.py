from typing import Dict, List
import uuid

from elmos_mature_platform.types import (
    ThreatModelAsset,
    DataFlow,
    ThreatRecord,
    ThreatCategory,
    ThreatSeverity,
    ThreatStatus
)

class ThreatModelingEngine:
    def __init__(self):
        self._assets: Dict[str, ThreatModelAsset] = {}
        self._flows: Dict[str, DataFlow] = {}
        self._threats: Dict[str, ThreatRecord] = {}

    def register_asset(self, asset: ThreatModelAsset) -> str:
        """Registers a new asset in the threat model."""
        self._assets[asset.asset_id] = asset
        return asset.asset_id

    def register_data_flow(self, flow: DataFlow) -> str:
        """Registers a new data flow between two existing assets."""
        if flow.source_asset not in self._assets:
            raise ValueError(f"Source asset {flow.source_asset} not found")
        if flow.target_asset not in self._assets:
            raise ValueError(f"Target asset {flow.target_asset} not found")
        
        self._flows[flow.flow_id] = flow
        return flow.flow_id

    def identify_threat(self, threat: ThreatRecord) -> str:
        """Manually registers a new threat."""
        self._threats[threat.threat_id] = threat
        threat.risk_score = self.calculate_risk_score(threat.threat_id)
        return threat.threat_id

    def auto_discover_threats(self, asset_id: str) -> List[ThreatRecord]:
        """Auto-generates threats for an asset based on its properties and flows."""
        if asset_id not in self._assets:
            raise ValueError(f"Asset {asset_id} not found")
        
        asset = self._assets[asset_id]
        discovered_threats = []
        
        # Public assets
        if asset.trust_level == "public":
            spoofing = ThreatRecord(
                threat_id=f"auto-{uuid.uuid4()}",
                title=f"Spoofing on public asset {asset.name}",
                category=ThreatCategory.SPOOFING,
                severity=ThreatSeverity.HIGH,
                affected_assets=[asset_id]
            )
            discovered_threats.append(spoofing)
            
            dos = ThreatRecord(
                threat_id=f"auto-{uuid.uuid4()}",
                title=f"DoS on public asset {asset.name}",
                category=ThreatCategory.DENIAL_OF_SERVICE,
                severity=ThreatSeverity.HIGH,
                affected_assets=[asset_id]
            )
            discovered_threats.append(dos)

        # Flows involving this asset (as source or target)
        relevant_flows = [f for f in self._flows.values() if f.source_asset == asset_id or f.target_asset == asset_id]
        
        for flow in relevant_flows:
            # Unencrypted flows
            if not flow.encrypted:
                info_disc = ThreatRecord(
                    threat_id=f"auto-{uuid.uuid4()}",
                    title=f"Information disclosure on unencrypted flow {flow.flow_id}",
                    category=ThreatCategory.INFORMATION_DISCLOSURE,
                    severity=ThreatSeverity.MEDIUM,
                    affected_assets=[asset_id],
                    affected_flows=[flow.flow_id]
                )
                discovered_threats.append(info_disc)
                
                tampering = ThreatRecord(
                    threat_id=f"auto-{uuid.uuid4()}",
                    title=f"Tampering on unencrypted flow {flow.flow_id}",
                    category=ThreatCategory.TAMPERING,
                    severity=ThreatSeverity.MEDIUM,
                    affected_assets=[asset_id],
                    affected_flows=[flow.flow_id]
                )
                discovered_threats.append(tampering)

            # Unauthenticated flows
            if not flow.authenticated:
                spoofing_flow = ThreatRecord(
                    threat_id=f"auto-{uuid.uuid4()}",
                    title=f"Spoofing on unauthenticated flow {flow.flow_id}",
                    category=ThreatCategory.SPOOFING,
                    severity=ThreatSeverity.HIGH,
                    affected_assets=[asset_id],
                    affected_flows=[flow.flow_id]
                )
                discovered_threats.append(spoofing_flow)
                
                eop = ThreatRecord(
                    threat_id=f"auto-{uuid.uuid4()}",
                    title=f"Elevation of Privilege on unauthenticated flow {flow.flow_id}",
                    category=ThreatCategory.ELEVATION_OF_PRIVILEGE,
                    severity=ThreatSeverity.HIGH,
                    affected_assets=[asset_id],
                    affected_flows=[flow.flow_id]
                )
                discovered_threats.append(eop)

            # Restricted data in flow
            if flow.data_classification == "restricted":
                restricted_info = ThreatRecord(
                    threat_id=f"auto-{uuid.uuid4()}",
                    title=f"High risk information disclosure on restricted data flow {flow.flow_id}",
                    category=ThreatCategory.INFORMATION_DISCLOSURE,
                    severity=ThreatSeverity.CRITICAL,
                    affected_assets=[asset_id],
                    affected_flows=[flow.flow_id]
                )
                discovered_threats.append(restricted_info)
        
        for threat in discovered_threats:
            self.identify_threat(threat)
            
        return discovered_threats

    def analyze_attack_surface(self) -> Dict:
        """Analyzes and summarizes the attack surface."""
        external_facing = sum(1 for a in self._assets.values() if a.trust_level in ("public", "dmz"))
        unencrypted_flows = sum(1 for f in self._flows.values() if not f.encrypted)
        unauth_flows = sum(1 for f in self._flows.values() if not f.authenticated)
        high_risk_threats = sum(1 for t in self._threats.values() if t.severity in (ThreatSeverity.CRITICAL, ThreatSeverity.HIGH) and t.status not in (ThreatStatus.MITIGATED, ThreatStatus.ACCEPTED))
        
        return {
            "total_assets": len(self._assets),
            "external_facing_count": external_facing,
            "unencrypted_flows": unencrypted_flows,
            "unauthenticated_flows": unauth_flows,
            "high_risk_threats": high_risk_threats
        }

    def mitigate_threat(self, threat_id: str, mitigation: str) -> ThreatRecord:
        """Applies a mitigation to a threat."""
        if threat_id not in self._threats:
            raise ValueError(f"Threat {threat_id} not found")
        
        threat = self._threats[threat_id]
        if threat.status == ThreatStatus.ACCEPTED:
            raise ValueError("Cannot mitigate an already accepted threat")
            
        threat.mitigation = mitigation
        threat.status = ThreatStatus.MITIGATED
        return threat

    def accept_threat(self, threat_id: str, justification: str) -> ThreatRecord:
        """Accepts the risk of a threat."""
        if threat_id not in self._threats:
            raise ValueError(f"Threat {threat_id} not found")
            
        threat = self._threats[threat_id]
        threat.mitigation = justification
        threat.status = ThreatStatus.ACCEPTED
        return threat

    def calculate_risk_score(self, threat_id: str) -> float:
        """Calculates risk score based on severity and exposure."""
        if threat_id not in self._threats:
            raise ValueError(f"Threat {threat_id} not found")
            
        threat = self._threats[threat_id]
        
        severity_weights = {
            ThreatSeverity.CRITICAL: 10,
            ThreatSeverity.HIGH: 7,
            ThreatSeverity.MEDIUM: 4,
            ThreatSeverity.LOW: 2,
            ThreatSeverity.INFO: 1
        }
        
        exposure_weights = {
            "public": 4,
            "dmz": 3,
            "internal": 2,
            "restricted": 1
        }
        
        max_exposure = 0
        if not threat.affected_assets:
            max_exposure = 2
        else:
            for a_id in threat.affected_assets:
                if a_id in self._assets:
                    asset = self._assets[a_id]
                    weight = exposure_weights.get(asset.trust_level, 2)
                    if weight > max_exposure:
                        max_exposure = weight
                        
        severity_weight = severity_weights.get(threat.severity, 1)
        
        return float(severity_weight * max_exposure)

    def get_stride_summary(self) -> Dict:
        """Returns count of threats per STRIDE category."""
        summary = {cat: 0 for cat in ThreatCategory}
        for threat in self._threats.values():
            summary[threat.category] += 1
        return {cat.value: count for cat, count in summary.items()}

    def get_threat_model_report(self) -> Dict:
        """Generates a full threat modeling report."""
        status_counts = {status.value: 0 for status in ThreatStatus}
        severity_counts = {severity.value: 0 for severity in ThreatSeverity}
        
        for t in self._threats.values():
            status_counts[t.status.value] += 1
            severity_counts[t.severity.value] += 1
            
        avg_risk = 0.0
        if self._threats:
            avg_risk = sum(t.risk_score for t in self._threats.values()) / len(self._threats)
            
        return {
            "assets_count": len(self._assets),
            "flows_count": len(self._flows),
            "threats_by_status": status_counts,
            "threats_by_severity": severity_counts,
            "attack_surface": self.analyze_attack_surface(),
            "average_risk_score": avg_risk
        }

    def get_unmitigated_critical_threats(self) -> List[ThreatRecord]:
        """Returns unmitigated critical or high threats."""
        return [
            t for t in self._threats.values()
            if t.severity in (ThreatSeverity.CRITICAL, ThreatSeverity.HIGH) and
            t.status not in (ThreatStatus.MITIGATED, ThreatStatus.ACCEPTED)
        ]
