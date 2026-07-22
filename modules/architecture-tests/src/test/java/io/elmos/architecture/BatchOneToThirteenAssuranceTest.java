package io.elmos.architecture;

import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class BatchOneToThirteenAssuranceTest {
    private final Path root = Path.of(System.getProperty("basedir")).resolve("../..").normalize();

    @Test
    void javaGenericExecutionFailsClosedWithoutFabricatedEvidence() throws IOException {
        String controller = Files.readString(root.resolve(
                "apps/java-engine-worker/src/main/java/io/elmos/worker/EngineController.java"));
        String registry = Files.readString(root.resolve(
                "apps/java-engine-worker/src/main/java/io/elmos/worker/EngineJobRegistry.java"));
        String production = controller + registry;

        assertTrue(production.contains("NOT_CONFIGURED_FAIL_CLOSED"));
        assertTrue(production.contains("customerCodeExecuted"));
        assertTrue(production.contains("JobStatus.FAILED"));
        assertFalse(production.contains("artifact://simulated"));
        assertFalse(production.contains("SIMULATED_ONLY"));
    }

    @Test
    void explicitlySimulatedDemoCannotBeConfusedWithWorkerExecution() throws IOException {
        String demo = Files.readString(root.resolve(
                "modules/application/src/main/java/io/elmos/application/BatchOneDemoService.java"));
        assertTrue(demo.contains("batch1-simulator"));
        assertTrue(demo.contains("no customer code was executed"));
        assertTrue(demo.contains("new DemoRunResult"));
        assertTrue(demo.contains("events.size(),true)"));
    }

    @Test
    void batchMigrationsAreContinuousAndUnique() throws IOException {
        Path migrations = root.resolve("modules/persistence/src/main/resources/db/migration");
        Set<String> actual;
        try (var files = Files.list(migrations)) {
            actual = files.filter(path -> path.getFileName().toString().matches("V\\d+__.+\\.sql"))
                    .map(path -> path.getFileName().toString().replaceFirst("__.*", ""))
                    .collect(Collectors.toSet());
        }
        Set<String> expected = IntStream.rangeClosed(1, 47).mapToObj(value -> "V" + value)
                .collect(Collectors.toSet());
        assertEquals(expected, actual);
    }

    @Test
    void skillPacksAndVerificationReportsCoverAllBatches() throws IOException {
        assertEquals(37, countSkills(root.resolve("agent-skills/build")));
        assertTrue(countSkills(root.resolve("agent-skills/runtime")) >= 1647,
                "runtime Skill count must not fall below the 1,647-Skill baseline; additive Skills are allowed");
        assertEquals(32, countSkills(root.resolve("agent-skills/build-test-feedback")));
        assertEquals(9, countJsonSchemas(root.resolve("contracts/repair-loop-schema")));
        assertEquals(35, countSkills(root.resolve("agent-skills/behavioral-equivalence")));
        assertEquals(11, countJsonSchemas(root.resolve("contracts/behavior-equivalence-schema")));
        assertEquals(39, countSkills(root.resolve("agent-skills/production-hardening")));
        assertEquals(12, countJsonSchemas(root.resolve("contracts/production-hardening-schema")));
        assertEquals(41, countSkills(root.resolve("agent-skills/production-cutover")));
        assertEquals(14, countJsonSchemas(root.resolve("contracts/production-cutover-schema")));
        assertEquals(50, countSkills(root.resolve("agent-skills/enterprise-platform")));
        assertEquals(16, countJsonSchemas(root.resolve("contracts/enterprise-platform-schema")));
        assertEquals(70, countSkills(root.resolve("agent-skills/commercial-loop")));
        assertEquals(16, countJsonSchemas(root.resolve("contracts/commercial-loop-schema")));
        assertEquals(60, countSkills(root.resolve("agent-skills/ecosystem-growth")));
        assertEquals(18, countJsonSchemas(root.resolve("contracts/ecosystem-growth-schema")));
        assertEquals(65, countSkills(root.resolve("agent-skills/company-operating-system")));
        assertEquals(4, countJsonSchemas(root.resolve("contracts/company-operating-system-schema")));
        assertEquals(67, countSkills(root.resolve("agent-skills/agent-workforce")));
        assertEquals(4, countJsonSchemas(root.resolve("contracts/agent-workforce-schema")));
        assertEquals(76, countSkills(root.resolve("agent-skills/vertical-solutions")));
        assertEquals(4, countJsonSchemas(root.resolve("contracts/vertical-solution-schema")));
        assertEquals(77, countSkills(root.resolve("agent-skills/group-integration")));
        assertEquals(4, countJsonSchemas(root.resolve("contracts/group-integration-schema")));
        assertTrue(countSkills(root.resolve(".agents/skills")) >= 425,
                "repository Skill count must not fall below the 425-Skill baseline; additive Skills are allowed");
        assertTrue(Files.isRegularFile(root.resolve(".agents/skills/elmos-project-synthesis/SKILL.md")));
        assertTrue(countSkillsWithPrefix(root.resolve(".agents/skills"), "tst-") >= 52,
                "strict test Skill count must not fall below the 52-Skill Batch 1-37 baseline; additive suites are allowed");
        assertEquals(9, countJsonSchemas(root.resolve("schemas/test-suite")));
        assertTrue(Files.isRegularFile(root.resolve("docs/test-suite/IMPORT_AUDIT.md")));
        assertTrue(Files.isRegularFile(root.resolve("docs/test-suite/VALIDATION.md")));
        int[] matureSkillCounts = {20, 20, 22, 20, 20, 22, 22, 18, 36, 22, 22, 24, 20, 22, 20, 20, 22};
        int[] matureSchemaCounts = {3, 4, 6, 7, 8, 10, 13, 12, 25, 4, 4, 4, 4, 4, 4, 4, 4};
        for (int offset = 0; offset < matureSkillCounts.length; offset++) {
            int batch = 29 + offset;
            assertEquals(matureSkillCounts[offset], countSkillsWithPrefix(
                    root.resolve(".agents/skills"), "b" + batch + "-"));
            assertEquals(matureSchemaCounts[offset], countJsonSchemas(
                    root.resolve("schemas/batch" + batch)));
        }

        for (String report : Set.of("batch-1-4-verification.md", "batch-5-8-verification.md",
                "batch-9-10-verification.md", "batch-11-verification.md",
                "batch-12-verification.md", "batch-13-verification.md", "batch-14-verification.md",
                "batch-15-verification.md", "batch-16-verification.md", "batch-17-verification.md",
                "batch-18-verification.md", "batch-19-verification.md", "batch-20-verification.md",
                "batch-21-verification.md", "batch-22-verification.md", "batch-23-verification.md",
                "batch-24-verification.md", "batch-25-verification.md", "batch-26-verification.md",
                "batch-8-build-test-repair-loop.md", "batch-9-behavioral-equivalence.md",
                "batch-10-production-hardening.md", "batch-11-production-cutover.md",
                "batch-12-enterprise-platform.md", "batch-13-commercial-loop.md",
                "batch-13-commercial-loop-acceptance-checklist.md",
                "batch-14-product-ecosystem-growth.md", "batch-14-growth-verification.md",
                "batch-14-growth-acceptance-checklist.md",
                "batch-15-company-operating-verification.md",
                "batch-16-agent-workforce-verification.md",
                "batch-17-vertical-solutions-verification.md",
                "batch-18-group-integration-verification.md",
                "mature-product-batches-29-45-verification.md")) {
            Path path = root.resolve("docs").resolve(report);
            assertTrue(Files.isRegularFile(path), () -> "missing verification report: " + report);
            String contents = Files.readString(path);
            assertTrue(contents.contains("NOT_RUN") || contents.contains("not run")
                            || contents.contains("external") || contents.contains("现场"),
                    () -> "verification report must preserve external evidence boundaries: " + report);
        }
    }

    @Test
    void batch36DeveloperWorkflowIsExecutableAndCertificationRemainsExternal() throws IOException {
        Path source = root.resolve("modules/developer-workflow/src/main/java/io/elmos/developerworkflow");
        String production;
        try (var files = Files.walk(source)) {
            production = files.filter(path -> path.getFileName().toString().endsWith(".java"))
                    .map(path -> {
                        try { return Files.readString(path); }
                        catch (IOException error) { throw new java.io.UncheckedIOException(error); }
                    }).collect(Collectors.joining("\n"));
        }
        assertTrue(production.contains("class IdeProtocolGateway"));
        assertTrue(production.contains("class SourceTargetNavigator"));
        assertTrue(production.contains("class OwnershipPolicyEngine"));
        assertTrue(production.contains("class TelemetryPrivacyFilter"));
        assertTrue(production.contains("class DeveloperWorkflowCli"));
        assertFalse(production.contains("ProcessBuilder"));
        assertFalse(production.contains("Runtime.getRuntime"));

        String rootPom = Files.readString(root.resolve("pom.xml"));
        assertTrue(rootPom.contains("<module>modules/developer-workflow</module>"));
        String result = Files.readString(root.resolve(
                "developer-experience-packs/elmos-local-developer-workflow/certification/gate-result.json"));
        String certification = Files.readString(root.resolve(
                "developer-experience-packs/elmos-local-developer-workflow/certification/certification.json"));
        assertTrue(result.contains("\"certification_decision\": \"NOT_CERTIFIED\""));
        assertTrue(result.contains("\"certification_requested\": false"));
        assertTrue(certification.contains("\"status\": \"experimental\""));
        assertTrue(certification.contains("NOT_RUN"));

        String generator = Files.readString(root.resolve("skills/generate_mature_product_batches_35_45.py"));
        assertFalse(generator.contains("    36: {"));
        assertFalse(generator.contains("    37: {"));
    }

    @Test
    void batch37MarketplaceIsExecutableAndCertificationRemainsExternal() throws IOException {
        Path source = root.resolve("modules/extension-marketplace/src/main/java/io/elmos/marketplace");
        String production;
        try (var files = Files.walk(source)) {
            production = files.filter(path -> path.getFileName().toString().endsWith(".java"))
                    .map(path -> {
                        try { return Files.readString(path); }
                        catch (IOException error) { throw new java.io.UncheckedIOException(error); }
                    }).collect(Collectors.joining("\n"));
        }
        assertTrue(production.contains("class ExtensionManifestValidator"));
        assertTrue(production.contains("class SandboxPolicyEngine"));
        assertTrue(production.contains("class SupplyChainVerifier"));
        assertTrue(production.contains("class DependencyLockResolver"));
        assertTrue(production.contains("class ReleaseLifecycleService"));
        assertTrue(production.contains("class InstallationRegistry"));
        assertTrue(production.contains("class MarketplaceClosureControls"));
        assertTrue(production.contains("Signature.getInstance(\"Ed25519\")"));
        assertFalse(production.contains("ProcessBuilder"));
        assertFalse(production.contains("Runtime.getRuntime"));

        String rootPom = Files.readString(root.resolve("pom.xml"));
        assertTrue(rootPom.contains("<module>modules/extension-marketplace</module>"));
        String coreResult = Files.readString(root.resolve(
                "marketplace-packs/elmos-local-extension-marketplace/certification/gate-result.json"));
        String closureResult = Files.readString(root.resolve(
                "marketplace-packs/elmos-local-extension-marketplace/certification/closure-gate-result.json"));
        String evidence = Files.readString(root.resolve(
                "marketplace-packs/elmos-local-extension-marketplace/certification/evidence.json"));
        assertTrue(coreResult.contains("\"certification_decision\": \"NOT_CERTIFIED\""));
        assertTrue(coreResult.contains("\"certification_requested\": false"));
        assertTrue(closureResult.contains("\"closure_decision\": \"NOT_CERTIFIED\""));
        assertTrue(closureResult.contains("\"closure_complete\": false"));
        assertTrue(evidence.contains("\"external_evidence_status\": \"NOT_RUN\""));

        String corpusGate = Files.readString(root.resolve("scripts/batch37/_common.py"));
        assertTrue(corpusGate.contains("validate_attested_corpus"));
        assertTrue(corpusGate.contains("approved-sandbox"));
        String generator = Files.readString(root.resolve("skills/generate_mature_product_batches_35_45.py"));
        assertFalse(generator.contains("    37: {"));
    }

    @Test
    void enterprisePlatformCannotExecuteCustomerCodeOrProductionOperations() throws IOException {
        Path source = root.resolve("modules/enterprise-platform/src/main/java");
        String production;
        try (var files = Files.walk(source)) {
            production = files.filter(path -> path.getFileName().toString().endsWith(".java"))
                    .map(path -> {
                        try { return Files.readString(path); }
                        catch (IOException error) { throw new java.io.UncheckedIOException(error); }
                    }).collect(Collectors.joining("\n"));
        }
        assertFalse(production.contains("ProcessBuilder"));
        assertFalse(production.contains("Runtime.getRuntime"));
        assertTrue(production.contains("TenancyIdentityAuthority"));
        assertTrue(production.contains("AuthorizationAuditAuthority"));
        assertTrue(production.contains("RunnerSecurityAuthority"));
        assertTrue(production.contains("ModelCostAuthority"));
        assertTrue(production.contains("DataGovernanceAuthority"));
        assertTrue(production.contains("DeploymentAuthority"));
        assertTrue(production.contains("EnterpriseAcceptanceAuthority"));
        assertTrue(production.contains("Batch 12 control plane cannot execute production operations"));
        assertTrue(production.contains("enterprise delivery readiness requires T-G and all externally evidenced modes"));
        assertTrue(production.contains("production_operation_executed"));
    }

    @Test
    void behavioralEquivalenceCoreCannotExecuteCustomerCodeOrAuthorizeCutover() throws IOException {
        Path source = root.resolve("modules/behavior-equivalence/src/main/java");
        String production;
        try (var files = Files.walk(source)) {
            production = files.filter(path -> path.getFileName().toString().endsWith(".java"))
                    .map(path -> {
                        try { return Files.readString(path); }
                        catch (IOException error) { throw new java.io.UncheckedIOException(error); }
                    }).collect(Collectors.joining("\n"));
        }
        assertFalse(production.contains("ProcessBuilder"));
        assertFalse(production.contains("Runtime.getRuntime"));
        assertTrue(production.contains("DualRuntimeAuthority"));
        assertTrue(production.contains("DifferentialExecutionAuthority"));
        assertTrue(production.contains("eligibleForCutover"));
        assertTrue(production.contains("Batch 9 never authorizes cutover"));
    }

    @Test
    void productionHardeningCoreCannotExecuteProductionOrAuthorizeCutover() throws IOException {
        Path source = root.resolve("modules/production-hardening/src/main/java");
        String production;
        try (var files = Files.walk(source)) {
            production = files.filter(path -> path.getFileName().toString().endsWith(".java"))
                    .map(path -> {
                        try { return Files.readString(path); }
                        catch (IOException error) { throw new java.io.UncheckedIOException(error); }
                    }).collect(Collectors.joining("\n"));
        }
        assertFalse(production.contains("ProcessBuilder"));
        assertFalse(production.contains("Runtime.getRuntime"));
        assertTrue(production.contains("EnvironmentCalibrationAuthority"));
        assertTrue(production.contains("PerformanceAuthority"));
        assertTrue(production.contains("SecurityAuthority"));
        assertTrue(production.contains("ReliabilityAuthority"));
        assertTrue(production.contains("ObservabilityAuthority"));
        assertTrue(production.contains("ReleaseAuthority"));
        assertTrue(production.contains("Batch 10 never declares production completion or cutover eligibility"));
    }

    @Test
    void productionCutoverCoreCannotExecutePrivilegedProductionChanges() throws IOException {
        Path source = root.resolve("modules/production-cutover/src/main/java");
        String production;
        try (var files = Files.walk(source)) {
            production = files.filter(path -> path.getFileName().toString().endsWith(".java"))
                    .map(path -> {
                        try { return Files.readString(path); }
                        catch (IOException error) { throw new java.io.UncheckedIOException(error); }
                    }).collect(Collectors.joining("\n"));
        }
        assertFalse(production.contains("ProcessBuilder"));
        assertFalse(production.contains("Runtime.getRuntime"));
        assertTrue(production.contains("TopologySchemaAuthority"));
        assertTrue(production.contains("DataMigrationAuthority"));
        assertTrue(production.contains("TrafficAuthority"));
        assertTrue(production.contains("IntegrationAuthority"));
        assertTrue(production.contains("RollbackIncidentAuthority"));
        assertTrue(production.contains("HypercareAcceptanceAuthority"));
        assertTrue(production.contains("RetirementAuthority"));
        assertTrue(production.contains("policy state machine cannot execute production changes"));
        assertTrue(production.contains("migration completion requires C-G, target truth and legacy decommission"));
    }

    @Test
    void frontendWorkerCannotExecuteHostCommandsAndFailsClosedWithoutRunners() throws IOException {
        Path source = root.resolve("engines/frontend-client-engine/src");
        String production;
        try (var files = Files.walk(source)) {
            production = files.filter(path -> path.getFileName().toString().endsWith(".ts"))
                    .map(path -> {
                        try { return Files.readString(path); }
                        catch (IOException error) { throw new java.io.UncheckedIOException(error); }
                    }).collect(Collectors.joining("\n"));
        }
        assertFalse(production.contains("node:child_process"));
        assertFalse(production.contains("from \"child_process\""));
        assertTrue(production.contains("RUNNER_REQUIRED_FAIL_CLOSED"));
        assertTrue(production.contains("RUNNER_NOT_CONFIGURED"));
        assertTrue(production.contains("customerCodeExecuted: false"));
    }

    @Test
    void databaseDataWorkerCannotUseJdbcHostCommandsOrFabricateExternalExecution() throws IOException {
        Path source = root.resolve("engines/database-data-engine/src/main/java");
        String production;
        try (var files = Files.walk(source)) {
            production = files.filter(path -> path.getFileName().toString().endsWith(".java"))
                    .map(path -> {
                        try { return Files.readString(path); }
                        catch (IOException error) { throw new java.io.UncheckedIOException(error); }
                    }).collect(Collectors.joining("\n"));
        }
        assertFalse(production.contains("java.sql"));
        assertFalse(production.contains("ProcessBuilder"));
        assertFalse(production.contains("Runtime.getRuntime"));
        assertTrue(production.contains("DATABASE_RUNNER_REQUIRED"));
        assertTrue(production.contains("customerCodeExecuted"));
        assertTrue(production.contains("\"NOT_RUN\""));
    }

    @Test
    void infrastructureWorkerCannotUseProviderSdksHostCommandsOrFabricateExternalExecution() throws IOException {
        Path source = root.resolve("engines/infrastructure-engine/src/main/java");
        String production;
        try (var files = Files.walk(source)) {
            production = files.filter(path -> path.getFileName().toString().endsWith(".java"))
                    .map(path -> {
                        try { return Files.readString(path); }
                        catch (IOException error) { throw new java.io.UncheckedIOException(error); }
                    }).collect(Collectors.joining("\n"));
        }
        assertFalse(production.contains("ProcessBuilder"));
        assertFalse(production.contains("Runtime.getRuntime"));
        assertFalse(production.contains("software.amazon.awssdk"));
        assertFalse(production.contains("com.azure"));
        assertFalse(production.contains("com.google.cloud"));
        assertFalse(production.contains("io.kubernetes.client"));
        assertTrue(production.contains("INFRASTRUCTURE_RUNNER_REQUIRED"));
        assertTrue(production.contains("customerInfrastructureChanged"));
        assertTrue(production.contains("\"NOT_RUN\""));
    }

    @Test
    void securityWorkerCannotRunHostScannersAcceptRiskOrFabricateCertification() throws IOException {
        Path source = root.resolve("engines/security-compliance-engine/src/main/java");
        String production;
        try (var files = Files.walk(source)) {
            production = files.filter(path -> path.getFileName().toString().endsWith(".java"))
                    .map(path -> {
                        try { return Files.readString(path); }
                        catch (IOException error) { throw new java.io.UncheckedIOException(error); }
                    }).collect(Collectors.joining("\n"));
        }
        assertFalse(production.contains("ProcessBuilder"));
        assertFalse(production.contains("Runtime.getRuntime"));
        assertFalse(production.contains("software.amazon.awssdk"));
        assertFalse(production.contains("io.kubernetes.client"));
        assertTrue(production.contains("SECURITY_TEST_AUTHORIZATION_REQUIRED"));
        assertTrue(production.contains("evidenceFabricated"));
        assertTrue(production.contains("externalCertificationGranted"));
        assertTrue(production.contains("riskAcceptedByAgent"));
        assertTrue(production.contains("\"NOT_RUN\""));
    }

    @Test
    void testQualityWorkerCannotRunHostTestsModifyGateOrFabricateResults() throws IOException {
        Path source = root.resolve("engines/test-quality-engine/src/main/java");
        String production;
        try (var files = Files.walk(source)) {
            production = files.filter(path -> path.getFileName().toString().endsWith(".java"))
                    .map(path -> {
                        try { return Files.readString(path); }
                        catch (IOException error) { throw new java.io.UncheckedIOException(error); }
                    }).collect(Collectors.joining("\n"));
        }
        assertFalse(production.contains("ProcessBuilder"));
        assertFalse(production.contains("Runtime.getRuntime"));
        assertFalse(production.contains("java.sql"));
        assertFalse(production.contains("node:child_process"));
        assertTrue(production.contains("TEST_QUALITY_RUNNER_REQUIRED"));
        assertTrue(production.contains("customerCodeExecuted"));
        assertTrue(production.contains("evidenceFabricated"));
        assertTrue(production.contains("workerModifiedGate"));
        assertTrue(production.contains("aiTestAutoPromoted"));
        assertTrue(production.contains("notRunTreatedAsPass"));
        assertTrue(production.contains("\"NOT_RUN\""));
    }

    @Test
    void mainframeWorkerIsLeasedFailClosedAndCannotActAsCutoverAuthority() throws IOException {
        Path source = root.resolve("engines/mainframe-engine/src/main/java");
        String production;
        try (var files = Files.walk(source)) {
            production = files.filter(path -> path.getFileName().toString().endsWith(".java"))
                    .map(path -> {
                        try { return Files.readString(path); }
                        catch (IOException error) { throw new java.io.UncheckedIOException(error); }
                    }).collect(Collectors.joining("\n"));
        }
        assertFalse(production.contains("ProcessBuilder"));
        assertFalse(production.contains("Runtime.getRuntime"));
        assertFalse(production.contains("java.sql"));
        assertTrue(production.contains("MAINFRAME_RUNNER_REQUIRED"));
        assertTrue(production.contains("MAINFRAME_LEASE_REQUIRED"));
        assertTrue(production.contains("productionStateChanged"));
        assertTrue(production.contains("evidenceFabricated"));
        assertTrue(production.contains("SUBMIT_ARBITRARY_JCL"));
        assertTrue(production.contains("NOT_CONFIGURED"));

        String control = Files.readString(root.resolve(
                "apps/control-plane/src/main/java/io/elmos/controlplane/MainframeController.java"));
        assertTrue(control.contains("/api/v1/mainframe"));
        assertFalse(control.contains("@RequestMapping(\"/engine/v1\")"));
        assertTrue(control.contains("AUTO_SWITCH_DATA_AUTHORITY"));

        assertEquals(18, Set.of(
                "mainframe-engine-contract-and-zos-runner", "mainframe-estate-source-dataset-and-runtime-discovery",
                "cobol-copybook-semantic-symbol-and-data-layout-graph", "jcl-procedure-scheduler-and-batch-flow-analyzer",
                "cics-transaction-program-and-resource-modernizer", "ims-tm-db-message-and-hierarchical-data-modernizer",
                "db2-vsam-file-and-mainframe-data-access-modernizer", "mainframe-business-rule-extraction-and-domain-slicing",
                "mainframe-target-profile-and-modernization-planner", "mainframe-api-event-and-compatibility-facade-builder",
                "cobol-modularization-refactor-and-language-transformer", "mainframe-batch-restart-checkpoint-and-scheduler-modernizer",
                "terminal-3270-bms-mfs-and-user-journey-modernizer", "mainframe-data-replication-cdc-and-data-ownership-controller",
                "mainframe-devsecops-build-promotion-and-release-modernizer", "mainframe-test-generation-semantic-equivalence-and-validation",
                "parallel-run-cutover-rollback-and-decommission-orchestrator", "mainframe-elmos-unified-evidence-integration")
                .stream().filter(name -> Files.isRegularFile(root.resolve("agent-skills/runtime").resolve(name).resolve("SKILL.md"))).count());
        assertTrue(Files.readString(root.resolve("modules/persistence/src/main/resources/db/migration/V19__mainframe_core_legacy_modernization.sql"))
                .contains("FORCE ROW LEVEL SECURITY"));
    }

    @Test
    void enterpriseIntegrationWorkerIsLeasedFailClosedAndCannotActAsCutoverAuthority() throws IOException {
        Path source = root.resolve("engines/enterprise-integration-engine/src/main/java");
        String production;
        try (var files = Files.walk(source)) {
            production = files.filter(path -> path.getFileName().toString().endsWith(".java"))
                    .map(path -> {
                        try { return Files.readString(path); }
                        catch (IOException error) { throw new java.io.UncheckedIOException(error); }
                    }).collect(Collectors.joining("\n"));
        }
        assertFalse(production.contains("ProcessBuilder"));
        assertFalse(production.contains("Runtime.getRuntime"));
        assertFalse(production.contains("java.sql"));
        assertTrue(production.contains("INTEGRATION_RUNNER_REQUIRED"));
        assertTrue(production.contains("INTEGRATION_LEASE_REQUIRED"));
        assertTrue(production.contains("productionStateChanged"));
        assertTrue(production.contains("evidenceFabricated"));
        assertTrue(production.contains("PURGE_PRODUCTION_QUEUE"));
        assertTrue(production.contains("RESET_PRODUCTION_OFFSET"));
        assertTrue(production.contains("NOT_CONFIGURED"));

        String control = Files.readString(root.resolve(
                "apps/control-plane/src/main/java/io/elmos/controlplane/EnterpriseIntegrationController.java"));
        assertTrue(control.contains("/api/v1/integration"));
        assertFalse(control.contains("@RequestMapping(\"/engine/v1\")"));
        assertTrue(control.contains("AUTO_CUTOVER"));
        assertTrue(control.contains("AUTO_DECOMMISSION"));

        assertEquals(18, Set.of(
                "enterprise-integration-engine-contract-and-worker", "integration-estate-route-endpoint-and-runtime-discovery",
                "canonical-integration-contract-route-and-message-ir", "integration-target-profile-and-migration-planner",
                "esb-soa-flow-mapping-and-adapter-modernizer", "ibm-mq-queue-channel-transaction-and-dlq-modernizer",
                "kafka-topic-partition-consumer-and-stream-modernizer", "rabbitmq-exchange-quorum-stream-and-delivery-modernizer",
                "api-gateway-policy-lifecycle-and-facade-modernizer", "event-driven-architecture-cloudevents-and-event-governance",
                "schema-registry-contract-evolution-and-code-generation", "edi-as2-mft-b2b-partner-modernizer",
                "workflow-bpmn-saga-and-process-orchestration-modernizer", "integration-security-identity-certificate-and-nonrepudiation",
                "integration-observability-trace-replay-and-operational-readiness", "integration-contract-equivalence-validator",
                "parallel-bridge-dual-publish-cutover-and-decommission", "integration-elmos-unified-evidence-integration")
                .stream().filter(name -> Files.isRegularFile(root.resolve("agent-skills/runtime").resolve(name).resolve("SKILL.md"))).count());
        String v21 = Files.readString(root.resolve(
                "modules/persistence/src/main/resources/db/migration/V21__enterprise_integration_middleware_modernization.sql"));
        assertTrue(v21.contains("FORCE ROW LEVEL SECURITY"));
        assertTrue(v21.contains("ALTER TABLE message_contracts"));
    }

    @Test
    void enterpriseSuiteWorkerIsLeasedFailClosedAndCannotActAsCutoverAuthority() throws IOException {
        Path source = root.resolve("engines/enterprise-suite-engine/src/main/java");
        String production;
        try (var files = Files.walk(source)) {
            production = files.filter(path -> path.getFileName().toString().endsWith(".java"))
                    .map(path -> {
                        try { return Files.readString(path); }
                        catch (IOException error) { throw new java.io.UncheckedIOException(error); }
                    }).collect(Collectors.joining("\n"));
        }
        assertFalse(production.contains("ProcessBuilder"));
        assertFalse(production.contains("Runtime.getRuntime"));
        assertFalse(production.contains("java.sql"));
        assertTrue(production.contains("SUITE_RUNNER_REQUIRED"));
        assertTrue(production.contains("SUITE_LEASE_REQUIRED"));
        assertTrue(production.contains("productionStateChanged"));
        assertTrue(production.contains("evidenceFabricated"));
        assertTrue(production.contains("financialDifferenceAccepted"));
        assertTrue(production.contains("sodConflictAccepted"));
        assertTrue(production.contains("NOT_CONFIGURED"));

        String control = Files.readString(root.resolve(
                "apps/control-plane/src/main/java/io/elmos/controlplane/EnterpriseSuiteController.java"));
        assertTrue(control.contains("/api/v1/enterprise-suite"));
        assertFalse(control.contains("@RequestMapping(\"/engine/v1\")"));
        assertTrue(control.contains("AUTO_CUTOVER"));
        assertTrue(control.contains("AUTO_DECOMMISSION"));

        assertEquals(18, Set.of(
                "enterprise-suite-engine-contract-and-worker", "suite-estate-configuration-extension-and-usage-discovery",
                "business-process-capability-and-process-mining-graph", "customization-extension-clean-core-and-technical-debt-classifier",
                "enterprise-canonical-master-data-and-business-object-model", "suite-target-profile-and-transformation-planner",
                "sap-ecc-s4hana-clean-core-modernizer", "oracle-ebs-fusion-suite-modernizer",
                "dynamics365-dataverse-power-platform-modernizer", "salesforce-org-metadata-and-extension-modernizer",
                "master-data-governance-golden-record-and-crosswalk-engine", "suite-data-migration-history-archive-and-reconciliation",
                "suite-integration-api-event-and-extension-decoupling", "workflow-rule-report-analytics-and-process-modernizer",
                "suite-identity-role-segregation-of-duties-and-control-validator", "suite-business-process-test-and-semantic-equivalence-engine",
                "suite-alm-parallel-run-cutover-and-decommission-orchestrator", "enterprise-suite-elmos-unified-evidence-integration")
                .stream().filter(name -> Files.isRegularFile(root.resolve("agent-skills/runtime").resolve(name).resolve("SKILL.md"))).count());
        String v23 = Files.readString(root.resolve(
                "modules/persistence/src/main/resources/db/migration/V23__enterprise_suite_modernization.sql"));
        assertTrue(v23.contains("FORCE ROW LEVEL SECURITY"));
        assertTrue(v23.contains("suite_cutover_plans"));
        assertTrue(v23.contains("suite_decommission_plans"));
    }

    @Test
    void commercialLoopCannotExecuteExternalCommercialOperations() throws IOException {
        Path source = root.resolve("modules/commercial-loop/src/main/java");
        String production;
        try (var files = Files.walk(source)) {
            production = files.filter(path -> path.getFileName().toString().endsWith(".java"))
                    .map(path -> {
                        try { return Files.readString(path); }
                        catch (IOException error) { throw new java.io.UncheckedIOException(error); }
                    }).collect(Collectors.joining("\n"));
        }
        assertFalse(production.contains("ProcessBuilder"));
        assertFalse(production.contains("Runtime.getRuntime"));
        assertTrue(production.contains("SalesPocAuthority"));
        assertTrue(production.contains("QuoteContractAuthority"));
        assertTrue(production.contains("OnboardingDeliveryAuthority"));
        assertTrue(production.contains("SupportSuccessAuthority"));
        assertTrue(production.contains("PartnerAuthority"));
        assertTrue(production.contains("OperationsEconomicsAuthority"));
        assertTrue(production.contains("ScaleAcceptanceAuthority"));
        assertTrue(production.contains("Batch 13 control plane cannot execute commercial operations"));
        assertTrue(production.contains("commercial scale readiness requires B13-G and complete external evidence"));
        assertTrue(production.contains("commercial_operation_executed"));
    }

    @Test
    void compositeControlRemainsReadEvaluateOnlyAndNotAnExecutionEngine() throws IOException {
        String controller = Files.readString(root.resolve(
                "apps/control-plane/src/main/java/io/elmos/controlplane/CompositeController.java"));
        assertTrue(controller.contains("/api/v1/composite"));
        assertFalse(controller.contains("/engine/v1"));
        assertFalse(controller.contains("OpenRewrite"));
        assertFalse(controller.contains("Roslyn"));
        assertFalse(controller.contains("LibCST"));
    }

    private long countSkills(Path directory) throws IOException {
        try (var files = Files.walk(directory)) {
            return files.filter(path -> path.getFileName().toString().equals("SKILL.md")).count();
        }
    }

    private long countJsonSchemas(Path directory) throws IOException {
        try (var files = Files.list(directory)) {
            return files.filter(path -> path.getFileName().toString().endsWith(".schema.json")).count();
        }
    }

    private long countSkillsWithPrefix(Path directory, String prefix) throws IOException {
        try (var files = Files.list(directory)) {
            return files.filter(Files::isDirectory)
                    .filter(path -> path.getFileName().toString().startsWith(prefix))
                    .filter(path -> Files.isRegularFile(path.resolve("SKILL.md")))
                    .count();
        }
    }
}
