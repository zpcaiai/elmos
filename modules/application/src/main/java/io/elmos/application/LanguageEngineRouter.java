package io.elmos.application;

import io.elmos.engine.api.EngineApi;

import java.util.Locale;
import java.util.Map;
import java.util.Objects;

public final class LanguageEngineRouter {
    public enum LanguageEngine { JAVA, DOTNET, PYTHON, FRONTEND_CLIENT, DATABASE_DATA, INFRASTRUCTURE, SECURITY_COMPLIANCE, TEST_QUALITY, MAINFRAME, ENTERPRISE_INTEGRATION, ENTERPRISE_SUITE, SOFTWARE_DELIVERY_PLATFORM, AI_PLATFORM, EDGE_IOT_INDUSTRIAL, OPERATIONS_SRE_ITSM, ENTERPRISE_ARCHITECTURE }

    private final Map<LanguageEngine, ModernizationEnginePort> engines;

    public LanguageEngineRouter(Map<LanguageEngine, ModernizationEnginePort> engines) {
        this.engines = Map.copyOf(engines);
    }

    public ModernizationEnginePort require(LanguageEngine engine) {
        return Objects.requireNonNull(engines.get(engine), () -> "engine not configured: " + engine);
    }

    public ModernizationEnginePort requireForLanguage(String language) {
        var normalized = Objects.requireNonNull(language, "language").trim().toUpperCase(Locale.ROOT);
        return switch (normalized) {
            case "JAVA" -> require(LanguageEngine.JAVA);
            case "C#", "CSHARP", "C_SHARP", "VISUAL_BASIC", "VB", "DOTNET", ".NET" -> require(LanguageEngine.DOTNET);
            case "PYTHON", "PY", "CPYTHON" -> require(LanguageEngine.PYTHON);
            case "JAVASCRIPT", "JS", "TYPESCRIPT", "TS", "HTML", "CSS", "FRONTEND", "FRONTEND_CLIENT" ->
                    require(LanguageEngine.FRONTEND_CLIENT);
            case "SQL", "PLSQL", "PL/SQL", "TSQL", "T-SQL", "PLPGSQL", "DATABASE",
                    "DATABASE_DATA", "DATA_PLATFORM", "BI_SEMANTIC" -> require(LanguageEngine.DATABASE_DATA);
            case "INFRASTRUCTURE", "CLOUD_INFRASTRUCTURE", "CLOUD", "IAC", "TERRAFORM",
                    "OPENTOFU", "KUBERNETES", "K8S", "SERVERLESS", "VM", "BARE_METAL" ->
                    require(LanguageEngine.INFRASTRUCTURE);
            case "SECURITY", "SECURITY_COMPLIANCE", "SECURITY_AND_COMPLIANCE", "APPSEC", "DEVSECOPS" ->
                    require(LanguageEngine.SECURITY_COMPLIANCE);
            case "TEST", "TEST_QUALITY", "TEST QUALITY", "QUALITY_ENGINEERING", "QUALITY ENGINEERING",
                    "QUALITY_ASSURANCE", "QUALITY ASSURANCE", "QE", "QA" ->
                    require(LanguageEngine.TEST_QUALITY);
            case "MAINFRAME", "IBM_Z", "IBM Z", "ZOS", "Z/OS", "COBOL", "PLI", "PL/I",
                    "JCL", "CICS", "IMS", "DB2_ZOS", "VSAM", "3270" -> require(LanguageEngine.MAINFRAME);
            case "ENTERPRISE_INTEGRATION", "ENTERPRISE INTEGRATION", "INTEGRATION", "MIDDLEWARE",
                    "ESB", "SOA", "IBM_MQ", "IBM MQ", "KAFKA", "RABBITMQ", "JMS",
                    "API_GATEWAY", "API GATEWAY", "EDI", "MFT", "B2B", "AS2", "BPM" ->
                    require(LanguageEngine.ENTERPRISE_INTEGRATION);
            case "ENTERPRISE_SUITE", "ENTERPRISE SUITE", "ERP", "CRM", "HCM", "SCM", "EPM",
                    "SAP", "SAP_ECC", "SAP ECC", "S4HANA", "S/4HANA", "ORACLE_EBS", "ORACLE EBS",
                    "ORACLE_FUSION", "ORACLE FUSION", "DYNAMICS_365", "DYNAMICS 365", "DATAVERSE",
                    "POWER_PLATFORM", "POWER PLATFORM", "SALESFORCE" -> require(LanguageEngine.ENTERPRISE_SUITE);
            case "SOFTWARE_DELIVERY_PLATFORM", "SOFTWARE DELIVERY PLATFORM", "PLATFORM_ENGINEERING",
                    "PLATFORM ENGINEERING", "INTERNAL_DEVELOPER_PLATFORM", "IDP", "CI_CD", "CICD" ->
                    require(LanguageEngine.SOFTWARE_DELIVERY_PLATFORM);
            case "AI_PLATFORM", "AI PLATFORM", "MLOPS", "LLMOPS", "GENERATIVE_AI", "GENAI", "RAG", "AGENTIC_AI" ->
                    require(LanguageEngine.AI_PLATFORM);
            case "EDGE_IOT_INDUSTRIAL", "EDGE IOT INDUSTRIAL", "OT", "IOT", "INDUSTRIAL", "OPC_UA",
                    "OPC UA", "MQTT", "SPARKPLUG", "PLC", "SCADA" -> require(LanguageEngine.EDGE_IOT_INDUSTRIAL);
            case "OPERATIONS_SRE_ITSM", "OPERATIONS SRE ITSM", "OPERATIONS", "SRE", "ITSM", "AIOPS",
                    "INCIDENT_MANAGEMENT" -> require(LanguageEngine.OPERATIONS_SRE_ITSM);
            case "ENTERPRISE_ARCHITECTURE", "ENTERPRISE ARCHITECTURE", "EA", "APPLICATION_PORTFOLIO",
                    "APPLICATION PORTFOLIO", "TECHNOLOGY_PORTFOLIO", "ARCHIMATE", "TOGAF" ->
                    require(LanguageEngine.ENTERPRISE_ARCHITECTURE);
            default -> throw new IllegalArgumentException("unsupported language engine: " + language);
        };
    }

    public EngineApi.JobResponse scan(String language, EngineApi.JobRequest request) {
        return requireForLanguage(language).scan(request);
    }

    public EngineApi.JobResponse plan(String language, EngineApi.JobRequest request) {
        return requireForLanguage(language).plan(request);
    }

    public EngineApi.JobResponse execute(String language, EngineApi.ExecuteStepRequest request) {
        return requireForLanguage(language).executeStep(request);
    }

    public EngineApi.JobResponse validate(String language, EngineApi.JobRequest request) {
        return requireForLanguage(language).validate(request);
    }
}
