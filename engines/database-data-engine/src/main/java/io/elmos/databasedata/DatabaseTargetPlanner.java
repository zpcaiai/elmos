package io.elmos.databasedata;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

import static io.elmos.databasedata.DatabaseDataModels.*;

public final class DatabaseTargetPlanner {
    public List<TargetCandidate> candidates(EstateProfile estate) {
        if (estate.evidenceRefs().isEmpty()) throw new IllegalArgumentException("estate evidence is required");
        var candidates = new ArrayList<TargetCandidate>();
        candidates.add(candidate(Strategy.IN_PLACE_UPGRADE, ModernizationTrack.OLTP_DATABASE,
                estate.source(), estate.source() + "_SUPPORTED_RELEASE", Feasibility.FEASIBLE,
                estate.proceduresCritical() ? List.of("VENDOR_PROCEDURE_COUPLING") : List.of()));
        candidates.add(candidate(Strategy.MANAGED_SAME_ENGINE, ModernizationTrack.OLTP_DATABASE,
                estate.source(), "MANAGED_" + estate.source(), estate.residencyRestricted()
                        ? Feasibility.PILOT_REQUIRED : Feasibility.FEASIBLE_WITH_ADAPTER,
                estate.residencyRestricted() ? List.of("DATA_RESIDENCY_REVIEW") : List.of("MANAGED_SERVICE_LIMITS")));

        if (estate.source() != DatabaseVendor.POSTGRESQL) {
            candidates.add(candidate(Strategy.HETEROGENEOUS_REPLATFORM, ModernizationTrack.OLTP_DATABASE,
                    estate.source(), "POSTGRESQL_REGISTRY_SELECTED", estate.proceduresCritical()
                            ? Feasibility.FEASIBLE_WITH_REDESIGN : Feasibility.PILOT_REQUIRED,
                    estate.proceduresCritical() ? List.of("PROCEDURE_REDESIGN") : List.of("DIALECT_CONVERSION")));
        }
        if (estate.analyticsContention()) {
            candidates.add(candidate(Strategy.ANALYTICS_OFFLOAD, ModernizationTrack.ANALYTICS_PLATFORM,
                    estate.source(), "LAKEHOUSE_CANDIDATE_SET", estate.logBasedCdcAvailable()
                            ? Feasibility.FEASIBLE_WITH_ADAPTER : Feasibility.PILOT_REQUIRED,
                    estate.logBasedCdcAvailable() ? List.of("CDC_PROVIDER_APPROVAL") : List.of("CDC_UNSUPPORTED")));
        }
        candidates.add(candidate(Strategy.LAKEHOUSE_MODERNIZATION, ModernizationTrack.ANALYTICS_PLATFORM,
                estate.source(), "ICEBERG_DELTA_PARQUET_COMPARISON", Feasibility.PILOT_REQUIRED,
                List.of("READER_WRITER_COMPATIBILITY")));
        candidates.add(candidate(Strategy.ANALYTICS_OFFLOAD, ModernizationTrack.BI_SEMANTIC,
                estate.source(), "TOOL_NEUTRAL_SEMANTIC_LAYER", Feasibility.PILOT_REQUIRED,
                List.of("METRIC_OWNER_APPROVAL", "BI_ROW_SECURITY")));
        return candidates.stream().sorted(Comparator.comparing((TargetCandidate value) -> value.track().ordinal())
                .thenComparing(value -> value.strategy().ordinal()).thenComparing(TargetCandidate::target)).toList();
    }

    private TargetCandidate candidate(Strategy strategy, ModernizationTrack track, DatabaseVendor source,
                                      String target, Feasibility feasibility, List<String> risks) {
        return new TargetCandidate(strategy, track, source, target, feasibility, risks,
                switch (track) {
                    case OLTP_DATABASE -> List.of("SCHEMA", "PROCEDURE", "QUERY_RESULT", "QUERY_PERFORMANCE",
                            "DATA_RECONCILIATION", "CDC", "CUTOVER");
                    case ANALYTICS_PLATFORM -> List.of("DATA_CONTRACT", "QUALITY", "COMPATIBILITY",
                            "LINEAGE", "RETENTION_DELETE");
                    case BI_SEMANTIC -> List.of("METRIC_DEFINITION", "NUMERIC_RESULT", "ROW_SECURITY",
                            "REFRESH", "USAGE");
                });
    }
}
