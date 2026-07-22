package io.elmos.application;

import io.elmos.engine.api.EngineApi;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class LanguageEngineRouterTest {
    @Test void routesJavaDotnetAndPythonWithoutMixingTenantPortfolios(){
        var java=new StubPort("ELMOS_JAVA"); var dotnet=new StubPort("ELMOS_DOTNET"); var python=new StubPort("ELMOS_PYTHON");
        var frontend=new StubPort("ELMOS_FRONTEND_CLIENT");
        var databaseData=new StubPort("ELMOS_DATABASE_DATA");
        var infrastructure=new StubPort("ELMOS_INFRASTRUCTURE");
        var security=new StubPort("ELMOS_SECURITY_COMPLIANCE");
        var testQuality=new StubPort("ELMOS_TEST_QUALITY");
        var mainframe=new StubPort("ELMOS_MAINFRAME");
        var integration=new StubPort("ELMOS_ENTERPRISE_INTEGRATION");
        var suite=new StubPort("ELMOS_ENTERPRISE_SUITE");
        var platform=new StubPort("ELMOS_SOFTWARE_DELIVERY_PLATFORM");
        var ai=new StubPort("ELMOS_AI_PLATFORM");
        var industrial=new StubPort("ELMOS_EDGE_IOT_INDUSTRIAL");
        var operations=new StubPort("ELMOS_OPERATIONS_SRE_ITSM");
        var enterpriseArchitecture=new StubPort("ELMOS_ENTERPRISE_ARCHITECTURE");
        var router=new LanguageEngineRouter(Map.ofEntries(
                Map.entry(LanguageEngineRouter.LanguageEngine.JAVA,java),
                Map.entry(LanguageEngineRouter.LanguageEngine.DOTNET,dotnet),
                Map.entry(LanguageEngineRouter.LanguageEngine.PYTHON,python),
                Map.entry(LanguageEngineRouter.LanguageEngine.FRONTEND_CLIENT,frontend),
                Map.entry(LanguageEngineRouter.LanguageEngine.DATABASE_DATA,databaseData),
                Map.entry(LanguageEngineRouter.LanguageEngine.INFRASTRUCTURE,infrastructure),
                Map.entry(LanguageEngineRouter.LanguageEngine.SECURITY_COMPLIANCE,security),
                Map.entry(LanguageEngineRouter.LanguageEngine.TEST_QUALITY,testQuality),
                Map.entry(LanguageEngineRouter.LanguageEngine.MAINFRAME,mainframe),
                Map.entry(LanguageEngineRouter.LanguageEngine.ENTERPRISE_INTEGRATION,integration),
                Map.entry(LanguageEngineRouter.LanguageEngine.ENTERPRISE_SUITE,suite),
                Map.entry(LanguageEngineRouter.LanguageEngine.SOFTWARE_DELIVERY_PLATFORM,platform),
                Map.entry(LanguageEngineRouter.LanguageEngine.AI_PLATFORM,ai),
                Map.entry(LanguageEngineRouter.LanguageEngine.EDGE_IOT_INDUSTRIAL,industrial),
                Map.entry(LanguageEngineRouter.LanguageEngine.OPERATIONS_SRE_ITSM,operations),
                Map.entry(LanguageEngineRouter.LanguageEngine.ENTERPRISE_ARCHITECTURE,enterpriseArchitecture)));
        assertSame(java,router.requireForLanguage("java"));
        assertSame(dotnet,router.requireForLanguage("C#"));
        assertSame(python,router.requireForLanguage("python"));
        assertSame(frontend,router.requireForLanguage("typescript"));
        assertSame(databaseData,router.requireForLanguage("PL/SQL"));
        assertSame(infrastructure,router.requireForLanguage("OpenTofu"));
        assertSame(security,router.requireForLanguage("DevSecOps"));
        assertSame(testQuality,router.requireForLanguage("quality assurance"));
        assertSame(mainframe,router.requireForLanguage("COBOL"));
        assertSame(integration,router.requireForLanguage("IBM MQ"));
        assertSame(integration,router.requireForLanguage("Kafka"));
        assertSame(integration,router.requireForLanguage("AS2"));
        assertSame(suite,router.requireForLanguage("SAP ECC"));
        assertSame(suite,router.requireForLanguage("Oracle Fusion"));
        assertSame(suite,router.requireForLanguage("Dynamics 365"));
        assertSame(suite,router.requireForLanguage("Salesforce"));
        assertSame(platform,router.requireForLanguage("platform engineering"));
        assertSame(ai,router.requireForLanguage("GenAI"));
        assertSame(industrial,router.requireForLanguage("OPC UA"));
        assertSame(operations,router.requireForLanguage("SRE"));
        assertSame(enterpriseArchitecture,router.requireForLanguage("TOGAF"));
        assertThrows(IllegalArgumentException.class,()->router.requireForLanguage("ruby"));

        var portfolio=new UnifiedMigrationPortfolio();
        var wave=portfolio.combine("portfolio-1",List.of(
                new UnifiedMigrationPortfolio.EnginePlan("org-1","portfolio-1","ELMOS_JAVA","java-plan",List.of("orders-api"),List.of("schema"),List.of("contract")),
                new UnifiedMigrationPortfolio.EnginePlan("org-1","portfolio-1","ELMOS_DOTNET","dotnet-plan",List.of("orders-api"),List.of("windows"),List.of("contract","windows-build")),
                new UnifiedMigrationPortfolio.EnginePlan("org-1","portfolio-1","ELMOS_PYTHON","python-plan",List.of("orders-api"),List.of("model"),List.of("model-behavior")),
                new UnifiedMigrationPortfolio.EnginePlan("org-1","portfolio-1","ELMOS_FRONTEND_CLIENT","frontend-plan",List.of("orders-api"),List.of("visual"),List.of("visual","accessibility","client-contract")),
                new UnifiedMigrationPortfolio.EnginePlan("org-1","portfolio-1","ELMOS_DATABASE_DATA","data-plan",List.of("orders-api"),List.of("cdc"),List.of("reconciliation","query-performance","bi-metric","governance")),
                new UnifiedMigrationPortfolio.EnginePlan("org-1","portfolio-1","ELMOS_INFRASTRUCTURE","infra-plan",List.of("orders-api"),List.of("network","state"),List.of("plan","slo","cost","restore","cutover")),
                new UnifiedMigrationPortfolio.EnginePlan("org-1","portfolio-1","ELMOS_SECURITY_COMPLIANCE","security-plan",List.of("orders-api"),List.of("identity","supply-chain","exposure"),List.of("threat-model","coverage","control-assessment","authorization")),
                new UnifiedMigrationPortfolio.EnginePlan("org-1","portfolio-1","ELMOS_TEST_QUALITY","test-plan",List.of("orders-api"),List.of("critical-risk","flaky","mutation"),List.of("discovery","contract","journey","effectiveness","release-confidence")),
                new UnifiedMigrationPortfolio.EnginePlan("org-1","portfolio-1","ELMOS_MAINFRAME","mainframe-plan",List.of("orders-api"),List.of("copybook","jcl","data-authority"),List.of("source-runtime","semantic-equivalence","parallel-run","cutover")),
                new UnifiedMigrationPortfolio.EnginePlan("org-1","portfolio-1","ELMOS_ENTERPRISE_INTEGRATION","integration-plan",List.of("orders-api"),List.of("unknown-consumer","ordering","partner"),List.of("contract","delivery","business-result","cutover")),
                new UnifiedMigrationPortfolio.EnginePlan("org-1","portfolio-1","ELMOS_ENTERPRISE_SUITE","suite-plan",List.of("orders-api"),List.of("master-data","sod","financial"),List.of("business-process","master-data","financial-reconciliation","cutover")),
                new UnifiedMigrationPortfolio.EnginePlan("org-1","portfolio-1","ELMOS_SOFTWARE_DELIVERY_PLATFORM","platform-plan",List.of("orders-api"),List.of("history","artifact"),List.of("scm","pipeline","platform-acceptance")),
                new UnifiedMigrationPortfolio.EnginePlan("org-1","portfolio-1","ELMOS_AI_PLATFORM","ai-plan",List.of("orders-api"),List.of("data","model","agent"),List.of("evaluation","responsible-ai","release")),
                new UnifiedMigrationPortfolio.EnginePlan("org-1","portfolio-1","ELMOS_EDGE_IOT_INDUSTRIAL","ot-plan",List.of("orders-api"),List.of("safety","offline"),List.of("sil","hil","site-cutover")),
                new UnifiedMigrationPortfolio.EnginePlan("org-1","portfolio-1","ELMOS_OPERATIONS_SRE_ITSM","ops-plan",List.of("orders-api"),List.of("slo","continuity"),List.of("incident","remediation","drill")),
                new UnifiedMigrationPortfolio.EnginePlan("org-1","portfolio-1","ELMOS_ENTERPRISE_ARCHITECTURE","ea-plan",List.of("orders-api"),List.of("portfolio","obsolescence"),List.of("option","decision","conformance"))));
        assertEquals(List.of("orders-api"),wave.sharedApiDependencies());
        assertEquals(16,wave.plans().size());
        var system=portfolio.combineSystem("portfolio-1",wave.plans(),List.of(
                new UnifiedMigrationPortfolio.DependencyEdge("java-plan","python-plan",UnifiedMigrationPortfolio.DependencyType.MODEL,"fraud-score-v2"),
                new UnifiedMigrationPortfolio.DependencyEdge("dotnet-plan","python-plan",UnifiedMigrationPortfolio.DependencyType.DATA,"orders-v3"),
                new UnifiedMigrationPortfolio.DependencyEdge("data-plan","frontend-plan",UnifiedMigrationPortfolio.DependencyType.BI_METRIC,"revenue-v3"),
                new UnifiedMigrationPortfolio.DependencyEdge("dotnet-plan","data-plan",UnifiedMigrationPortfolio.DependencyType.DATABASE_OBJECT,"orders-db-v3"),
                new UnifiedMigrationPortfolio.DependencyEdge("infra-plan","java-plan",UnifiedMigrationPortfolio.DependencyType.PLATFORM,"runtime-platform-v1"),
                new UnifiedMigrationPortfolio.DependencyEdge("data-plan","infra-plan",UnifiedMigrationPortfolio.DependencyType.DISASTER_RECOVERY_PLAN,"data-dr-v1"),
                new UnifiedMigrationPortfolio.DependencyEdge("security-plan","java-plan",UnifiedMigrationPortfolio.DependencyType.SECURITY_CONTROL,"ssdf-java-v1"),
                new UnifiedMigrationPortfolio.DependencyEdge("test-plan","security-plan",UnifiedMigrationPortfolio.DependencyType.TEST_EFFECTIVENESS,"quality-manifest-v1"),
                new UnifiedMigrationPortfolio.DependencyEdge("mainframe-plan","java-plan",UnifiedMigrationPortfolio.DependencyType.COPYBOOK_CONTRACT,"customer-layout-v1"),
                new UnifiedMigrationPortfolio.DependencyEdge("integration-plan","java-plan",UnifiedMigrationPortfolio.DependencyType.MESSAGE_CONTRACT,"order-events-v3"),
                new UnifiedMigrationPortfolio.DependencyEdge("suite-plan","integration-plan",UnifiedMigrationPortfolio.DependencyType.BUSINESS_PROCESS,"order-to-cash-v3"),
                new UnifiedMigrationPortfolio.DependencyEdge("infra-plan","security-plan",UnifiedMigrationPortfolio.DependencyType.TRUST_BOUNDARY,"prod-boundary-v1"),
                new UnifiedMigrationPortfolio.DependencyEdge("frontend-plan","dotnet-plan",UnifiedMigrationPortfolio.DependencyType.CLIENT_CONTRACT,"orders-api"),
                new UnifiedMigrationPortfolio.DependencyEdge("platform-plan","java-plan",UnifiedMigrationPortfolio.DependencyType.GOLDEN_PATH,"java-service-v3"),
                new UnifiedMigrationPortfolio.DependencyEdge("ai-plan","python-plan",UnifiedMigrationPortfolio.DependencyType.MODEL_RELEASE,"fraud-model-v3"),
                new UnifiedMigrationPortfolio.DependencyEdge("ot-plan","ops-plan",UnifiedMigrationPortfolio.DependencyType.SERVICE_TOPOLOGY,"plant-line-v2"),
                new UnifiedMigrationPortfolio.DependencyEdge("ops-plan","platform-plan",UnifiedMigrationPortfolio.DependencyType.SLO,"platform-slo-v2"),
                new UnifiedMigrationPortfolio.DependencyEdge("ea-plan","suite-plan",UnifiedMigrationPortfolio.DependencyType.CAPABILITY_MAP,"order-to-cash-v4")));
        var dependencyTypes = system.dependencyEdges().stream().map(UnifiedMigrationPortfolio.DependencyEdge::type).toList();
        assertEquals(18, dependencyTypes.size());
        assertTrue(dependencyTypes.containsAll(List.of(UnifiedMigrationPortfolio.DependencyType.GOLDEN_PATH,
                UnifiedMigrationPortfolio.DependencyType.MODEL_RELEASE, UnifiedMigrationPortfolio.DependencyType.SERVICE_TOPOLOGY,
                UnifiedMigrationPortfolio.DependencyType.SLO, UnifiedMigrationPortfolio.DependencyType.CAPABILITY_MAP)));
        assertThrows(IllegalArgumentException.class,()->portfolio.combineSystem("portfolio-1",wave.plans(),List.of(
                new UnifiedMigrationPortfolio.DependencyEdge("python-plan","unknown",UnifiedMigrationPortfolio.DependencyType.HTTP,"bad"))));
        assertThrows(IllegalArgumentException.class,()->portfolio.combine("portfolio-1",List.of(
                new UnifiedMigrationPortfolio.EnginePlan("org-1","portfolio-1","ELMOS_JAVA","a",List.of(),List.of(),List.of()),
                new UnifiedMigrationPortfolio.EnginePlan("org-2","portfolio-1","ELMOS_DOTNET","b",List.of(),List.of(),List.of()))));
    }

    private static final class StubPort implements ModernizationEnginePort {
        private final String name; StubPort(String name){this.name=name;}
        public EngineApi.Capabilities capabilities(){return new EngineApi.Capabilities("1.0",name,"1",List.of(),List.of(),List.of(),List.of(),List.of(),List.of(),List.of(),List.of(),List.of(),List.of(),Map.of());}
        public EngineApi.JobResponse scan(EngineApi.JobRequest request){return response("scan");}
        public EngineApi.JobResponse plan(EngineApi.JobRequest request){return response("plan");}
        public EngineApi.JobResponse executeStep(EngineApi.ExecuteStepRequest request){return response("execute");}
        public EngineApi.JobResponse validate(EngineApi.JobRequest request){return response("validate");}
        public EngineApi.JobResponse job(String organizationId,String jobId){return response(jobId);}
        public EngineApi.JobResponse cancel(String organizationId,String jobId){return response(jobId);}
        private static EngineApi.JobResponse response(String id){return new EngineApi.JobResponse("1.0",id,EngineApi.JobStatus.SUCCEEDED,List.of(),Map.of(),null);}
    }
}
