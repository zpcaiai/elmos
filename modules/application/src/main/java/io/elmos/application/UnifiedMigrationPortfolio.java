package io.elmos.application;

import java.util.List;
import java.util.Objects;

public final class UnifiedMigrationPortfolio {
    public enum DependencyType {
        HTTP, MESSAGE, DATA, MODEL, SHARED_DATABASE, FILE, PACKAGE,
        CLIENT_CONTRACT, BFF, DESIGN_SYSTEM, USER_JOURNEY,
        DATABASE_OBJECT, CDC_STREAM, DATA_ASSET, DATA_PRODUCT, BI_METRIC, DATA_LINEAGE,
        INFRASTRUCTURE_RESOURCE, PLATFORM, NETWORK_ROUTE, OBSERVABILITY_SIGNAL,
        COST_ALLOCATION, DISASTER_RECOVERY_PLAN,
        SECURITY_CONTROL, TRUST_BOUNDARY, IDENTITY_POLICY, SUPPLY_CHAIN,
        VULNERABILITY_EXPOSURE, DATA_PROTECTION, AUTHORIZATION_BOUNDARY,
        QUALITY_REQUIREMENT, QUALITY_RISK, TEST_COVERAGE, TEST_CONTRACT,
        TEST_ENVIRONMENT, TEST_DATA, TEST_EFFECTIVENESS, BUSINESS_JOURNEY,
        MAINFRAME_TRANSACTION, MAINFRAME_BATCH, COPYBOOK_CONTRACT, JCL_DATASET_FLOW,
        CICS_RESOURCE, IMS_HIERARCHY, MAINFRAME_DATA_AUTHORITY, MAINFRAME_RUNTIME_USAGE,
        INTEGRATION_ROUTE, MESSAGE_CONTRACT, EVENT_CONTRACT, DELIVERY_POLICY,
        API_GATEWAY_ROUTE, BROKER_CHANNEL, TRADING_PARTNER, WORKFLOW_PROCESS,
        MESSAGE_LINEAGE, SCHEMA_REGISTRY_SUBJECT,
        SUITE_MODULE, SUITE_CONFIGURATION, SUITE_CUSTOMIZATION, SUITE_EXTENSION,
        BUSINESS_CAPABILITY, BUSINESS_PROCESS, ENTERPRISE_BUSINESS_OBJECT,
        MASTER_DATA_AUTHORITY, MASTER_DATA_CROSSWALK, SUITE_ROLE, SOD_CONTROL,
        SUITE_REPORT, SUITE_ALM_ARTIFACT, FINANCIAL_RECONCILIATION,
        DELIVERY_VALUE_STREAM, SCM_REPOSITORY, PIPELINE_COMPONENT, ARTIFACT_PROMOTION,
        GOLDEN_PATH, SELF_SERVICE_OFFERING, PLATFORM_SCORECARD,
        AI_DATASET, FEATURE_CONTRACT, MODEL_RELEASE, PROMPT_CONTRACT, RAG_INDEX,
        AGENT_TOOL_PERMISSION, AI_EVALUATION, RESPONSIBLE_AI_DECISION,
        INDUSTRIAL_ASSET, INDUSTRIAL_TAG, PROTOCOL_ENDPOINT, DEVICE_IDENTITY,
        OTA_RELEASE, DIGITAL_TWIN, SITE_CUTOVER,
        SERVICE_TOPOLOGY, INCIDENT, CHANGE, SLO, RUNBOOK, REMEDIATION_POLICY, CONTINUITY_PLAN,
        ENTERPRISE_CONTEXT, CAPABILITY_MAP, APPLICATION_PORTFOLIO, TECHNOLOGY_STANDARD,
        ARCHITECTURE_DECISION, ARCHITECTURE_ROADMAP, ARCHITECTURE_CONFORMANCE
    }
    public record DependencyEdge(String fromPlanId, String toPlanId, DependencyType type, String contractRef) {
        public DependencyEdge {
            Objects.requireNonNull(fromPlanId); Objects.requireNonNull(toPlanId); Objects.requireNonNull(type); Objects.requireNonNull(contractRef);
        }
    }
    public record EnginePlan(String organizationId, String portfolioId, String engineName, String planId,
                             List<String> apiDependencies, List<String> risks, List<String> acceptanceGates) {
        public EnginePlan {
            Objects.requireNonNull(organizationId); Objects.requireNonNull(portfolioId); Objects.requireNonNull(engineName); Objects.requireNonNull(planId);
            apiDependencies=List.copyOf(apiDependencies); risks=List.copyOf(risks); acceptanceGates=List.copyOf(acceptanceGates);
        }
    }
    public record Wave(String portfolioId, List<EnginePlan> plans, List<String> sharedApiDependencies,
                       List<String> sharedRisks, List<String> sharedAcceptanceGates) {}
    public record SystemWave(Wave wave, List<DependencyEdge> dependencyEdges) {}

    public Wave combine(String portfolioId, List<EnginePlan> plans) {
        var copy=List.copyOf(plans);
        if(copy.isEmpty()) throw new IllegalArgumentException("portfolio requires at least one engine plan");
        if(copy.stream().anyMatch(plan->!plan.portfolioId().equals(portfolioId))) throw new IllegalArgumentException("portfolio mismatch");
        if(copy.stream().map(EnginePlan::organizationId).distinct().count()!=1) throw new IllegalArgumentException("cross-tenant portfolio is forbidden");
        return new Wave(portfolioId,copy,
                copy.stream().flatMap(plan->plan.apiDependencies().stream()).distinct().sorted().toList(),
                copy.stream().flatMap(plan->plan.risks().stream()).distinct().sorted().toList(),
                copy.stream().flatMap(plan->plan.acceptanceGates().stream()).distinct().sorted().toList());
    }

    public SystemWave combineSystem(String portfolioId, List<EnginePlan> plans, List<DependencyEdge> dependencyEdges) {
        var wave=combine(portfolioId,plans);
        var planIds=wave.plans().stream().map(EnginePlan::planId).collect(java.util.stream.Collectors.toUnmodifiableSet());
        var edges=List.copyOf(dependencyEdges);
        if(edges.stream().anyMatch(edge->!planIds.contains(edge.fromPlanId())||!planIds.contains(edge.toPlanId()))) {
            throw new IllegalArgumentException("cross-engine dependency must reference plans in the same tenant portfolio");
        }
        return new SystemWave(wave,edges.stream().sorted(java.util.Comparator.comparing(DependencyEdge::fromPlanId)
                .thenComparing(DependencyEdge::toPlanId).thenComparing(edge->edge.type().name()).thenComparing(DependencyEdge::contractRef)).toList());
    }
}
