package io.elmos.infrastructure;

import java.util.Map;

import static io.elmos.infrastructure.InfrastructureModels.EvidenceType;

public final class InfrastructureEvidenceMapper {
    public record Mapping(String scope, String engine, String schemaVersion,
                          String check, String risk, String costUnit) {}

    private static final Map<EvidenceType, Mapping> MAPPINGS = Map.ofEntries(
            Map.entry(EvidenceType.INFRASTRUCTURE_ESTATE, map("ELMOS / Infrastructure Estate", "ESTATE_COVERAGE_RISK", "INFRA_DISCOVERY_UNIT")),
            Map.entry(EvidenceType.CONTAINER_SUPPLY_CHAIN, map("ELMOS / Container Supply Chain", "WORKLOAD_SECURITY_RISK", "CONTAINER_BUILD")),
            Map.entry(EvidenceType.IAC_PLAN, map("ELMOS / Infrastructure Plan", "INFRASTRUCTURE_GOVERNANCE_RISK", "IAC_RESOURCE_PLAN")),
            Map.entry(EvidenceType.KUBERNETES_PLATFORM, map("ELMOS / Kubernetes Policy", "PLATFORM_POLICY_RISK", "KUBERNETES_CLUSTER_HOUR")),
            Map.entry(EvidenceType.OBSERVABILITY_PROFILE, map("ELMOS / Observability Coverage", "OPERATIONAL_VISIBILITY_RISK", "OBSERVABILITY_GB")),
            Map.entry(EvidenceType.SLO_RESULT, map("ELMOS / SLO", "RELIABILITY_RISK", "OBSERVABILITY_GB")),
            Map.entry(EvidenceType.COST_ALLOCATION, map("ELMOS / Cost Budget", "FINANCIAL_OPERATION_RISK", "INFRA_DISCOVERY_UNIT")),
            Map.entry(EvidenceType.RESILIENCE_RESULT, map("ELMOS / Resilience", "RECOVERY_RISK", "CHAOS_EXPERIMENT")),
            Map.entry(EvidenceType.BACKUP_RESTORE, map("ELMOS / Restore", "RECOVERY_RISK", "DR_TEST")),
            Map.entry(EvidenceType.MULTICLOUD_PORTABILITY, map("ELMOS / Portability", "PORTABILITY_RISK", "MULTICLOUD_TEST")),
            Map.entry(EvidenceType.INFRASTRUCTURE_CUTOVER, map("ELMOS / Infrastructure Cutover", "CUTOVER_RISK", "CUTOVER_OPERATION"))
    );

    public Mapping map(EvidenceType type) {
        Mapping result = MAPPINGS.get(type);
        if (result == null) throw new IllegalArgumentException("unsupported infrastructure evidence type: " + type);
        return result;
    }

    private static Mapping map(String check, String risk, String costUnit) {
        return new Mapping("CLOUD_INFRASTRUCTURE", "ELMOS_INFRASTRUCTURE", "elmos.infrastructure-evidence.v1", check, risk, costUnit);
    }
}
