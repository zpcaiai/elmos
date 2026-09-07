package io.elmos.cutover;

import static io.elmos.cutover.ProductionCutoverModels.*;

/**
 * Approved production evidence ports. Implementations observe or change production outside this
 * policy module; the module itself never routes traffic, writes customer data or destroys assets.
 */
public record ProductionCutoverAuthorities(
        TopologySchemaAuthority topologySchema,
        DataMigrationAuthority dataMigration,
        TrafficAuthority traffic,
        IntegrationAuthority integrations,
        RollbackIncidentAuthority rollbackIncident,
        HypercareAcceptanceAuthority hypercareAcceptance,
        RetirementAuthority retirement) {

    public ProductionCutoverAuthorities {
        ProductionCutoverModels.required(topologySchema, "topology/schema authority");
        ProductionCutoverModels.required(dataMigration, "data migration authority");
        ProductionCutoverModels.required(traffic, "traffic authority");
        ProductionCutoverModels.required(integrations, "integration authority");
        ProductionCutoverModels.required(rollbackIncident, "rollback/incident authority");
        ProductionCutoverModels.required(hypercareAcceptance, "hypercare/acceptance authority");
        ProductionCutoverModels.required(retirement, "retirement authority");
    }

    @FunctionalInterface public interface TopologySchemaAuthority { TopologySchemaEvidence observe(Request request); }
    @FunctionalInterface public interface DataMigrationAuthority { DataMigrationEvidence observe(Request request); }
    @FunctionalInterface public interface TrafficAuthority { TrafficAuthorityEvidence observe(Request request); }
    @FunctionalInterface public interface IntegrationAuthority { IntegrationEvidence observe(Request request); }
    @FunctionalInterface public interface RollbackIncidentAuthority { RollbackIncidentEvidence observe(Request request); }
    @FunctionalInterface public interface HypercareAcceptanceAuthority { HypercareAcceptanceEvidence observe(Request request); }
    @FunctionalInterface public interface RetirementAuthority { RetirementEvidence observe(Request request); }
}
