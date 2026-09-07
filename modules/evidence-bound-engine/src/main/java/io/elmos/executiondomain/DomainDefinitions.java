package io.elmos.executiondomain;

import io.elmos.engine.api.EngineApi.ErrorCode;
import io.elmos.engine.api.EngineApi.ExecutorType;

import java.util.List;
import java.util.Map;
import java.util.Set;

public final class DomainDefinitions {
    private DomainDefinitions() {}

    public static DomainEngineDefinition softwareDelivery() {
        return new DomainEngineDefinition(
                "ELMOS_SOFTWARE_DELIVERY_PLATFORM",
                List.of("GIT", "LEGACY_SCM", "CI_CD", "ARTIFACT_REGISTRY", "INTERNAL_DEVELOPER_PLATFORM"),
                List.of("CONSOLIDATE", "STANDARDIZE", "GOLDEN_PATH", "GITOPS", "SELF_SERVICE", "RETIRE"),
                List.of("REPOSITORY", "PIPELINE_COMPONENT", "ARTIFACT", "ENVIRONMENT_TEMPLATE", "GOLDEN_PATH"),
                List.of("SCM_ESTATE", "DELIVERY_VALUE_STREAM", "SOFTWARE_CATALOG", "DORA_SCORECARD"),
                List.of("SCM_MIGRATION", "CI_VALIDATION", "ARTIFACT_REGISTRY", "ENVIRONMENT", "PLATFORM_ACCEPTANCE"),
                List.of("GITHUB", "GITLAB", "AZURE_DEVOPS", "BITBUCKET", "SVN", "PERFORCE", "CLEARCASE",
                        "JENKINS", "TEKTON", "ARTIFACT_REGISTRY", "BACKSTAGE", "CDEVENTS", "GITOPS", "SURVEY"),
                List.of("HISTORY", "PIPELINE", "PROVENANCE", "ENVIRONMENT_DRIFT", "GITOPS", "DEVEX", "DORA"),
                Map.of("PLATFORM", List.of("DELIVERY_DISCOVERY", "VALUE_STREAM_BASELINING", "SCM_PLANNING",
                        "PLATFORM_CAPABILITY_DESIGNING", "GOLDEN_PATH_BUILDING", "PIPELINE_STANDARDIZING",
                        "ARTIFACT_GOVERNING", "ENVIRONMENT_AUTOMATING", "PORTAL_INTEGRATING", "PILOT_ONBOARDING",
                        "COHORT_MIGRATING", "PLATFORM_MEASURING", "CONTINUOUS_IMPROVEMENT")),
                Set.of("SCM_ESTATE_INCOMPLETE", "REPOSITORY_HISTORY_MISMATCH", "AUTHOR_IDENTITY_UNRESOLVED",
                        "PIPELINE_UNREPRODUCIBLE", "PIPELINE_COMPONENT_UNPINNED", "ARTIFACT_PROVENANCE_MISSING",
                        "ENVIRONMENT_DRIFTED", "GOLDEN_PATH_UNSUPPORTED", "PLATFORM_ADOPTION_LOW",
                        "PLATFORM_RELIABILITY_FAILED", "DORA_COVERAGE_INSUFFICIENT", "METRIC_GAMING_SUSPECTED",
                        "SELF_SERVICE_POLICY_BLOCKED", "DEPRECATION_BLOCKED"),
                Set.of(ExecutorType.DELIVERY_DISCOVERY, ExecutorType.SCM_MIGRATION, ExecutorType.PIPELINE_VALIDATION,
                        ExecutorType.ARTIFACT_PROMOTION, ExecutorType.ENVIRONMENT_LIFECYCLE,
                        ExecutorType.PLATFORM_ACCEPTANCE, ExecutorType.SELF_SERVICE_OPERATION),
                Map.of(
                        ExecutorType.SCM_MIGRATION, rule("scmMigrationAuthorization", ErrorCode.SELF_SERVICE_AUTHORIZATION_REQUIRED, "SCM migration plan and mirror authorization are required"),
                        ExecutorType.ARTIFACT_PROMOTION, rule("artifactPromotionAuthorization", ErrorCode.SELF_SERVICE_AUTHORIZATION_REQUIRED, "artifact promotion scope and retention authorization are required"),
                        ExecutorType.ENVIRONMENT_LIFECYCLE, rule("environmentAuthorization", ErrorCode.SELF_SERVICE_AUTHORIZATION_REQUIRED, "environment lease, data class and TTL approval are required"),
                        ExecutorType.SELF_SERVICE_OPERATION, rule("selfServiceAuthorization", ErrorCode.SELF_SERVICE_AUTHORIZATION_REQUIRED, "offering policy, quota and compensation authorization are required")),
                Set.of("deleteProductionRepository", "rewriteProductionHistory", "deleteReleaseTag",
                        "deleteProductionArtifact", "modifyProtectedBranch", "autoDeployProduction",
                        "autoApprovePlatformException", "forceGoldenPathAdoption", "returnLongLivedSecret"),
                ErrorCode.PLATFORM_RUNNER_REQUIRED, ErrorCode.PLATFORM_LEASE_REQUIRED,
                ErrorCode.PLATFORM_ESTATE_INCOMPLETE, ErrorCode.PLATFORM_PRODUCTION_APPROVAL_REQUIRED);
    }

    public static DomainEngineDefinition aiPlatform() {
        return new DomainEngineDefinition(
                "ELMOS_AI_PLATFORM",
                List.of("PREDICTIVE_ML", "FOUNDATION_MODEL", "LLM_APPLICATION", "RAG", "AGENTIC_AI"),
                List.of("REPRODUCE", "REGISTER", "SHADOW", "CANARY", "CHAMPION_CHALLENGER", "PRODUCTION", "RETIRE"),
                List.of("DATASET", "FEATURE", "MODEL", "PROMPT", "INDEX", "AGENT", "AI_RELEASE_BUNDLE"),
                List.of("AI_ESTATE", "FEATURE_PLATFORM", "MODEL_REGISTRY", "RAG_GRAPH", "AGENT_GRAPH"),
                List.of("AI_DISCOVERY", "CPU_TRAINING", "GPU_TRAINING", "ONLINE_INFERENCE", "LLM_EVALUATION", "RAG_SANDBOX", "AGENT_SANDBOX"),
                List.of("MLFLOW", "FEAST", "KUBEFLOW", "KSERVE", "INFERENCE_GATEWAY", "ENVOY_AI_GATEWAY",
                        "CLOUD_AI", "VECTOR_STORE", "AGENT_FRAMEWORK", "OPENTELEMETRY", "HUMAN_REVIEW"),
                List.of("DATA_LINEAGE", "FEATURE_PARITY", "REPRODUCIBILITY", "QUALITY", "GUARDRAIL", "RESPONSIBLE_AI", "COST"),
                Map.of("AI_SYSTEM", List.of("AI_DISCOVERY", "USE_CASE_REVIEW", "DATA_BASELINING", "FEATURE_DESIGNING",
                        "EXPERIMENTING", "TRAINING", "EVALUATING", "RISK_REVIEW", "REGISTRY_CANDIDATE", "APPROVED",
                        "SHADOW", "CANARY", "PRODUCTION", "MONITORING", "RETRAINING_OR_UPDATING")),
                Set.of("AI_USE_CASE_UNAPPROVED", "DATASET_UNTRACEABLE", "LABEL_QUALITY_INSUFFICIENT",
                        "FEATURE_SKEW_DETECTED", "TRAINING_UNREPRODUCIBLE", "MODEL_ARTIFACT_INCOMPLETE",
                        "EVALUATION_INSUFFICIENT", "JUDGE_UNCALIBRATED", "RAG_GROUNDING_FAILED", "AGENT_TOOL_RISK",
                        "GUARDRAIL_INSUFFICIENT", "FAIRNESS_RISK_UNRESOLVED", "PRODUCTION_DRIFT",
                        "AI_COST_BUDGET_EXCEEDED", "AI_INCIDENT", "ROLLBACK_REQUIRED", "DECOMMISSION_BLOCKED"),
                Set.of(ExecutorType.AI_DISCOVERY, ExecutorType.CPU_TRAINING, ExecutorType.GPU_TRAINING,
                        ExecutorType.AI_EVALUATION, ExecutorType.RAG_VALIDATION, ExecutorType.AGENT_SANDBOX,
                        ExecutorType.AI_DEPLOYMENT, ExecutorType.AI_MONITORING),
                Map.of(
                        ExecutorType.CPU_TRAINING, rule("trainingAuthorization", ErrorCode.AI_TRAINING_AUTHORIZATION_REQUIRED, "dataset, artifact and compute authorization are required"),
                        ExecutorType.GPU_TRAINING, rule("trainingAuthorization", ErrorCode.AI_TRAINING_AUTHORIZATION_REQUIRED, "dataset, artifact, GPU and budget authorization are required"),
                        ExecutorType.AGENT_SANDBOX, rule("agentToolApproval", ErrorCode.AGENT_TOOL_APPROVAL_REQUIRED, "tool allowlist, identity, budget and human approval policy are required"),
                        ExecutorType.AI_DEPLOYMENT, rule("aiDeploymentApproval", ErrorCode.AI_DEPLOYMENT_APPROVAL_REQUIRED, "release bundle, evaluation, safety, risk and cost approval are required")),
                Set.of("useUnapprovedProductionData", "loadUntrustedModelInControlPlane", "autoPublishProductionModel",
                        "grantAgentProductionWrite", "autoAcceptResponsibleAiRisk", "logSensitivePromptPlaintext",
                        "shadowSideEffect", "crossTenantCache"),
                ErrorCode.AI_RUNNER_REQUIRED, ErrorCode.AI_DATA_LEASE_REQUIRED,
                ErrorCode.AI_ESTATE_INCOMPLETE, ErrorCode.AI_DEPLOYMENT_APPROVAL_REQUIRED);
    }

    public static DomainEngineDefinition industrial() {
        return new DomainEngineDefinition(
                "ELMOS_EDGE_IOT_INDUSTRIAL",
                List.of("OT", "IOT", "PLC", "SCADA", "OPC_UA", "MQTT", "EDGE_AI"),
                List.of("KEEP", "GATEWAY", "OPC_UA", "MQTT", "EDGE", "CLOUD", "NONSTOP_CUTOVER", "RETIRE"),
                List.of("PLC_PROJECT", "TAG_CONTRACT", "DEVICE_ARTIFACT", "OTA_RELEASE", "TWIN", "SITE_FREEZE_MANIFEST"),
                List.of("INDUSTRIAL_ESTATE", "ASSET_MODEL", "PROTOCOL_GRAPH", "DIGITAL_TWIN", "SITE_CUTOVER"),
                List.of("PASSIVE_DISCOVERY", "PROTOCOL_VALIDATION", "EDGE_RUNTIME", "PLC_TEST", "HIL", "OTA_VALIDATION", "EDGE_AI"),
                List.of("OPCUA", "MQTT", "SPARKPLUG", "MODBUS", "INDUSTRIAL_PROTOCOLS", "ECLIPSE_DITTO",
                        "KUBEEDGE", "HISTORIAN", "OTA", "EDGE_AI", "VENDOR_PLC"),
                List.of("SAFETY", "SEMANTICS", "OFFLINE_AUTONOMY", "OTA_RECOVERY", "TWIN_CONSISTENCY", "SIL", "HIL"),
                Map.of("INDUSTRIAL", List.of("OT_DISCOVERY", "ASSET_CORRELATION", "SEMANTIC_MODELING",
                        "SAFETY_CLASSIFICATION", "TARGET_PLANNING", "EDGE_PREPARING", "PASSIVE_OBSERVATION",
                        "DIGITAL_SHADOW", "SHADOW_ANALYTICS", "ADVISORY_MODE", "LIMITED_COMMAND",
                        "CONTROLLED_CLOSED_LOOP", "PROGRESSIVE_SITE_CUTOVER", "STABILITY_HOLD",
                        "LEGACY_READ_ONLY", "DECOMMISSIONED")),
                Set.of("OT_ESTATE_INCOMPLETE", "UNKNOWN_PHYSICAL_ASSET", "PLC_PROJECT_RUNTIME_MISMATCH",
                        "TAG_SEMANTIC_UNKNOWN", "SAFETY_BOUNDARY_UNRESOLVED", "PROTOCOL_WRITE_RISK",
                        "DEVICE_IDENTITY_MISSING", "EDGE_OFFLINE_AUTONOMY_FAILED", "OTA_RECOVERY_FAILED",
                        "TWIN_STATE_DIVERGED", "TIME_SERIES_QUALITY_FAILED", "EDGE_AI_UNSAFE", "COMMAND_ACK_UNKNOWN",
                        "NONSTOP_VALIDATION_FAILED", "CUTOVER_PAUSED", "ROLLBACK_REQUIRED", "DECOMMISSION_BLOCKED"),
                Set.of(ExecutorType.OT_DISCOVERY, ExecutorType.PROTOCOL_VALIDATION,
                        ExecutorType.EDGE_RUNTIME_VALIDATION, ExecutorType.OTA_VALIDATION,
                        ExecutorType.EDGE_AI_VALIDATION, ExecutorType.SIL_VALIDATION,
                        ExecutorType.HIL_VALIDATION, ExecutorType.OT_COMMAND, ExecutorType.OT_CUTOVER),
                Map.of(
                        ExecutorType.OTA_VALIDATION, rule("otaAuthorization", ErrorCode.OT_COMMAND_APPROVAL_REQUIRED, "device, hardware, ring and recovery authorization are required"),
                        ExecutorType.OT_COMMAND, rule("localCommandApproval", ErrorCode.OT_COMMAND_APPROVAL_REQUIRED, "site-local policy and named human command approval are required"),
                        ExecutorType.OT_CUTOVER, rule("siteCutoverApproval", ErrorCode.OT_PRODUCTION_APPROVAL_REQUIRED, "read, write, safety, rollback and site owner approval are required")),
                Set.of("writeArbitraryPlc", "modifySafetyPlc", "downloadProductionPlcProgram", "clearScadaAlarm",
                        "bypassInterlock", "fleetWideOta", "exposeDeviceToPublicNetwork", "cloudRequiredForSafetyLoop",
                        "safetyRelatedOperation"),
                ErrorCode.OT_SITE_RUNNER_REQUIRED, ErrorCode.OT_LEASE_REQUIRED,
                ErrorCode.OT_ESTATE_INCOMPLETE, ErrorCode.OT_PRODUCTION_APPROVAL_REQUIRED);
    }

    public static DomainEngineDefinition operations() {
        return new DomainEngineDefinition(
                "ELMOS_OPERATIONS_SRE_ITSM",
                List.of("OPERATIONS", "SRE", "ITSM", "CMDB", "AIOPS", "BUSINESS_CONTINUITY"),
                List.of("OBSERVE", "CORRELATE", "RESTORE", "REMEDIATE", "IMPROVE", "CONTINUITY"),
                List.of("SERVICE_MODEL", "EVENT", "INCIDENT", "CHANGE", "RUNBOOK", "CONTINUITY_PLAN"),
                List.of("OPERATIONS_ESTATE", "SERVICE_TOPOLOGY", "INCIDENT_GRAPH", "OPERATIONS_COCKPIT"),
                List.of("OPERATIONS_DISCOVERY", "EVENT_CORRELATION", "INCIDENT_SIMULATION", "RUNBOOK_AUTOMATION", "CAPACITY_SIMULATION", "CONTINUITY_DRILL"),
                List.of("ITSM", "CMDB", "SERVICENOW_CSDM", "OPENTELEMETRY", "METRICS", "LOGS", "TRACES",
                        "PAGER", "CHAT", "STATUS_PAGE", "CLOUD", "DEPLOYMENT", "SECURITY", "BUSINESS_KPI"),
                List.of("TOPOLOGY", "ALERT_ACTIONABILITY", "INCIDENT_COMMAND", "SLO", "REMEDIATION", "CAPACITY", "CONTINUITY"),
                Map.of(
                        "OPERATIONS", List.of("OPERATIONS_DISCOVERY", "SERVICE_MODELING", "OBSERVABILITY_BASELINING",
                                "EVENT_NORMALIZING", "ALERT_GOVERNING", "OPERATIONAL_READINESS", "CONTINUOUS_OPERATIONS"),
                        "INCIDENT", List.of("DETECTED", "TRIAGED", "INCIDENT_DECLARED", "COMMAND_ESTABLISHED",
                                "MITIGATING", "SERVICE_RESTORED", "MONITORING", "RESOLVED", "POSTMORTEM_REQUIRED", "CLOSED")),
                Set.of("SERVICE_MODEL_INCOMPLETE", "UNKNOWN_SERVICE_OWNER", "TOPOLOGY_CONFLICT", "OBSERVABILITY_GAP",
                        "ALERT_STORM", "INCIDENT_COMMAND_MISSING", "CHANGE_CORRELATION_UNKNOWN", "RUNBOOK_STALE",
                        "AUTOMATION_UNSAFE", "SLO_DATA_INSUFFICIENT", "ERROR_BUDGET_EXHAUSTED", "ONCALL_OVERLOAD",
                        "CAPACITY_AT_RISK", "CONTINUITY_PLAN_UNTESTED", "CMDB_STALE"),
                Set.of(ExecutorType.OPERATIONS_DISCOVERY, ExecutorType.EVENT_CORRELATION,
                        ExecutorType.INCIDENT_SIMULATION, ExecutorType.RUNBOOK_AUTOMATION,
                        ExecutorType.CAPACITY_SIMULATION, ExecutorType.CONTINUITY_DRILL,
                        ExecutorType.OPERATIONS_REMEDIATION, ExecutorType.OPERATIONS_CHANGE),
                Map.of(
                        ExecutorType.OPERATIONS_REMEDIATION, rule("remediationApproval", ErrorCode.REMEDIATION_APPROVAL_REQUIRED, "bounded blast radius, verification, rollback and approval are required"),
                        ExecutorType.OPERATIONS_CHANGE, rule("changeApproval", ErrorCode.HIGH_RISK_CHANGE_APPROVAL_REQUIRED, "risk-classified change approval and business verification are required")),
                Set.of("autoCloseMajorIncident", "autoConfirmRootCause", "unboundedProductionCommand",
                        "autoApproveHighRiskChange", "deleteIncidentTimeline", "weakenSloToHideFailure",
                        "autoClosePostmortemAction", "autoStopBusinessService"),
                ErrorCode.OPERATIONS_RUNNER_REQUIRED, ErrorCode.OPERATIONS_LEASE_REQUIRED,
                ErrorCode.OPERATIONS_ESTATE_INCOMPLETE, ErrorCode.HIGH_RISK_CHANGE_APPROVAL_REQUIRED);
    }

    public static DomainEngineDefinition enterpriseArchitecture() {
        return new DomainEngineDefinition(
                "ELMOS_ENTERPRISE_ARCHITECTURE",
                List.of("ENTERPRISE_ARCHITECTURE", "BUSINESS_ARCHITECTURE", "APPLICATION_PORTFOLIO", "TECHNOLOGY_PORTFOLIO"),
                List.of("CURRENT", "TRANSITION", "TARGET", "INVEST", "CONTAIN", "RETIRE"),
                List.of("ARCHITECTURE_SNAPSHOT", "VIEW", "STANDARD", "ADR", "ROADMAP", "EVIDENCE_PACK"),
                List.of("ENTERPRISE_CONTEXT", "CAPABILITY_MAP", "EA_REPOSITORY", "PORTFOLIO", "ROADMAP"),
                List.of("PORTFOLIO_ANALYSIS", "ARCHITECTURE_GRAPH_ANALYSIS", "OPTION_EVALUATION", "ROADMAP_SIMULATION", "CONFORMANCE_VALIDATION"),
                List.of("TOGAF", "ARCHIMATE", "ISO_42010", "IT4IT", "OPEN_AGILE_ARCHITECTURE", "EA_REPOSITORY",
                        "CMDB", "SERVICE_CATALOG", "DATA_CATALOG", "TECHNOLOGY_RADAR", "PORTFOLIO_MANAGEMENT", "FINANCE", "MODELING_TOOL"),
                List.of("AUTHORITY", "CONFIDENCE", "CAPABILITY", "PORTFOLIO", "DEPENDENCY", "OPTION", "ROADMAP", "CONFORMANCE", "BENEFIT"),
                Map.of("ENTERPRISE_ARCHITECTURE", List.of("ENTERPRISE_CONTEXT_DISCOVERY", "CAPABILITY_MODELING",
                        "PORTFOLIO_DISCOVERY", "CURRENT_ARCHITECTURE_BASELINING", "ISSUE_AND_OPPORTUNITY_ANALYSIS",
                        "TARGET_OPTION_DESIGNING", "ARCHITECTURE_EVALUATING", "TARGET_APPROVING", "ROADMAP_PLANNING",
                        "INVESTMENT_ALIGNING", "IMPLEMENTATION_GOVERNING", "BENEFIT_VALIDATING", "ARCHITECTURE_EVOLVING")),
                Set.of("ENTERPRISE_CONTEXT_INCOMPLETE", "CAPABILITY_OWNER_UNKNOWN", "APPLICATION_OWNER_UNKNOWN",
                        "PORTFOLIO_DATA_LOW_CONFIDENCE", "CURRENT_ARCHITECTURE_STALE", "TARGET_ARCHITECTURE_INFEASIBLE",
                        "TRANSITION_STATE_MISSING", "STANDARD_CONFLICT", "EXCEPTION_EXPIRED", "DEPENDENCY_UNRESOLVED",
                        "INVESTMENT_BENEFIT_UNPROVEN", "ROADMAP_DEPENDENCY_CONFLICT", "DECISION_NOT_IMPLEMENTED",
                        "ARCHITECTURE_DRIFT", "DECOMMISSION_BLOCKED"),
                Set.of(ExecutorType.EA_DISCOVERY, ExecutorType.EA_ASSESSMENT,
                        ExecutorType.EA_OPTION_EVALUATION, ExecutorType.EA_ROADMAP_SIMULATION,
                        ExecutorType.EA_DECISION, ExecutorType.EA_CONFORMANCE),
                Map.of(
                        ExecutorType.EA_DECISION, rule("architectureDecisionApproval", ErrorCode.ARCHITECTURE_DECISION_APPROVAL_REQUIRED, "decision owner and risk-tier review approval are required"),
                        ExecutorType.EA_ROADMAP_SIMULATION, rule("investmentApproval", ErrorCode.INVESTMENT_APPROVAL_REQUIRED, "funding, dependency and benefit hypothesis approval are required")),
                Set.of("autoApproveInvestment", "autoRetireProductionSystem", "autoAcceptArchitectureException",
                        "modifyCapabilityOwner", "autoConfirmBenefit", "externalRadarBecomesPolicy", "deleteArchitectureDecision"),
                ErrorCode.EA_RUNNER_REQUIRED, ErrorCode.EA_LEASE_REQUIRED,
                ErrorCode.EA_ESTATE_INCOMPLETE, ErrorCode.ARCHITECTURE_DECISION_APPROVAL_REQUIRED);
    }

    private static DomainEngineDefinition.AuthorizationRule rule(String key, ErrorCode code, String message) {
        return new DomainEngineDefinition.AuthorizationRule(key, code, message);
    }
}
