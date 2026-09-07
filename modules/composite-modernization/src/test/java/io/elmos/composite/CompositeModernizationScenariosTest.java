package io.elmos.composite;

import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static io.elmos.composite.BusinessJourneyValidator.*;
import static io.elmos.composite.CompatibilityGovernance.*;
import static io.elmos.composite.CompositeModels.*;
import static io.elmos.composite.ContractCatalogService.*;
import static io.elmos.composite.DataMigrationController.*;
import static io.elmos.composite.ProgressiveTrafficController.*;
import static io.elmos.composite.ShadowTrafficValidator.*;
import static io.elmos.composite.SystemCutoverOrchestrator.*;
import static org.junit.jupiter.api.Assertions.*;

class CompositeModernizationScenariosTest {
    private static final Instant NOW = Instant.parse("2026-07-21T00:00:00Z");
    private static final LandscapeCoverage COMPLETE = new LandscapeCoverage(1, 1, 1, 1, 1, 1, 1, 1);

    @Test
    void scenario01_javaHttpProducerAndDotnetConsumerCannotHideBreakingRemoval() {
        ContractCatalogService service = new ContractCatalogService();
        ContractVersion current = contract(ContractType.HTTP_OPENAPI, "1.0.0", Language.JAVA,
                Map.of("id", "string", "displayName", "string"), Set.of("id"), Map.of(), Map.of());
        ContractVersion target = contract(ContractType.HTTP_OPENAPI, "2.0.0", Language.JAVA,
                Map.of("id", "string"), Set.of("id"), Map.of(), Map.of());
        CatalogDecision decision = service.evaluate(current, target,
                List.of(consumer("dotnet-billing", Language.DOTNET, false, true)), true, 0);

        assertEquals(Compatibility.BREAKING, decision.overall());
        assertTrue(decision.blockers().contains("CONTRACT_BREAKING"));
        assertFalse(decision.destructiveChangeAllowed());
    }

    @Test
    void scenario02_pythonMessageProducerPreservesJavaAndDotnetConsumerMatrix() {
        ContractVersion current = contract(ContractType.ASYNCAPI, "1.0.0", Language.PYTHON,
                Map.of("status", "string", "occurredAt", "string"), Set.of("status"),
                Map.of("status", Set.of("OPEN", "CLOSED")), Map.of("occurredAt", "date-time"));
        ContractVersion target = contract(ContractType.ASYNCAPI, "2.0.0", Language.PYTHON,
                Map.of("status", "string", "occurredAt", "string"), Set.of("status"),
                Map.of("status", Set.of("OPEN")), Map.of("occurredAt", "unix-seconds"));
        CatalogDecision decision = new ContractCatalogService().evaluate(current, target,
                List.of(consumer("java-orders", Language.JAVA, true, false),
                        consumer("dotnet-ledger", Language.DOTNET, true, false)), false, 0);

        assertEquals(2, decision.matrix().size());
        assertTrue(decision.matrix().stream().allMatch(entry -> entry.compatibility() == Compatibility.BREAKING));
        assertTrue(decision.matrix().getFirst().findings().stream().anyMatch(value -> value.startsWith("ENUM_VALUE_REMOVED")));
        assertTrue(decision.matrix().getFirst().findings().stream().anyMatch(value -> value.startsWith("FORMAT_CHANGED")));
    }

    @Test
    void scenario03_protobufFieldNumberChangeIsWireBreaking() {
        ContractVersion current = contract(ContractType.GRPC_PROTOBUF, "1.0.0", Language.DOTNET,
                Map.of("customer_id", "1:string"), Set.of("customer_id"), Map.of(), Map.of());
        ContractVersion target = contract(ContractType.GRPC_PROTOBUF, "1.1.0", Language.DOTNET,
                Map.of("customer_id", "2:string"), Set.of("customer_id"), Map.of(), Map.of());
        CatalogDecision decision = new ContractCatalogService().evaluate(current, target,
                List.of(consumer("python-risk", Language.PYTHON, true, false)), false, 0);

        assertEquals(Compatibility.BREAKING, decision.overall());
        assertTrue(decision.matrix().getFirst().findings().contains(
                "PROTOBUF_WIRE_FIELD_NUMBER_CHANGED:customer_id"));
    }

    @Test
    void scenario04_unknownExternalConsumerBlocksDestructiveContractChange() {
        ContractVersion current = contract(ContractType.HTTP_OPENAPI, "1.0.0", Language.JAVA,
                Map.of("id", "string"), Set.of("id"), Map.of(), Map.of());
        ContractVersion target = contract(ContractType.HTTP_OPENAPI, "2.0.0", Language.JAVA,
                Map.of("id", "string"), Set.of("id"), Map.of(), Map.of());
        Consumer unknown = new Consumer("external-mobile", Language.UNKNOWN, false, true,
                "1.0.0", "unknown", List.of());
        CatalogDecision decision = new ContractCatalogService().evaluate(current, target,
                List.of(unknown), true, 11);

        assertTrue(decision.blockers().contains("UNKNOWN_CONSUMER_BLOCKER"));
        assertTrue(decision.blockers().contains("OLD_CONTRACT_USAGE_PRESENT"));
        assertFalse(decision.destructiveChangeAllowed());
    }

    @Test
    void scenario05_stronglyConnectedServicesBecomeOneCompositeUnit() {
        List<SystemNode> nodes = List.of(node("java-a", Language.JAVA, NodeType.SERVICE),
                node("dotnet-b", Language.DOTNET, NodeType.SERVICE),
                node("python-c", Language.PYTHON, NodeType.SERVICE));
        SystemLandscape landscape = landscape(nodes, List.of(
                edge("java-a", "dotnet-b", EdgeType.CALLS_HTTP),
                edge("dotnet-b", "python-c", EdgeType.CALLS_GRPC),
                edge("python-c", "java-a", EdgeType.PUBLISHES_MESSAGE)));

        DependencyGraphAnalyzer.Analysis analysis = new DependencyGraphAnalyzer().analyze(landscape);
        assertEquals(1, analysis.cycles().size());
        assertEquals(Set.of("java-a", "dotnet-b", "python-c"), Set.copyOf(analysis.cycles().getFirst().nodeIds()));
        assertTrue(analysis.cycles().getFirst().compatibilityRuntimeRequired());
        assertThrows(UnsupportedOperationException.class, () -> landscape.nodes().add(node("x", Language.JAVA, NodeType.SERVICE)));
    }

    @Test
    void scenario06_sharedDatabaseWithMultipleWritersIsExplicitCoupling() {
        List<SystemNode> nodes = List.of(node("java-orders", Language.JAVA, NodeType.SERVICE),
                node("python-report", Language.PYTHON, NodeType.BATCH_JOB),
                node("orders-db", Language.NONE, NodeType.DATABASE));
        DependencyGraphAnalyzer.Analysis analysis = new DependencyGraphAnalyzer().analyze(landscape(nodes, List.of(
                edge("java-orders", "orders-db", EdgeType.WRITES_DATABASE),
                edge("python-report", "orders-db", EdgeType.WRITES_DATABASE))));

        assertEquals(List.of("java-orders", "python-report"), analysis.sharedDatabases().getFirst().writers());
        assertTrue(analysis.blockers().contains("SHARED_DATABASE_COUPLING"));
    }

    @Test
    void scenario07_sequentialDualWritePartialFailureNeverReportsSuccess() {
        WriteDecision decision = new DataMigrationController().evaluateDualWrite(
                new DualWriteAttempt(true, false, false, "order-7", false, false, true));

        assertEquals(WriteResult.PARTIAL_WRITE, decision.result());
        assertTrue(decision.blockers().contains("PARTIAL_SECONDARY_WRITE"));
        assertTrue(decision.blockers().contains("SEQUENTIAL_DUAL_WRITE_WITHOUT_RECOVERY"));
    }

    @Test
    void scenario08_cdcLagBlocksOtherwiseCompleteBackfillCutover() {
        DataCutoverResult result = new DataMigrationController().evaluateCutover(cutover(61, true, true));

        assertFalse(result.readCutoverAllowed());
        assertFalse(result.writeCutoverAllowed());
        assertTrue(result.blockers().contains("CDC_LAG_EXCEEDED"));
    }

    @Test
    void scenario09_shadowWriteWithoutSuppressionCannotEnterCanary() {
        SafetyPolicy policy = new SafetyPolicy(ShadowType.HTTP_MIRROR, true,
                SideEffectPolicy.UNSAFE_NOT_ALLOWED, Map.of("card", SensitiveDataAction.TOKENIZE),
                true, true, true, "retention-30d");
        DifferentialResult result = new ShadowTrafficValidator().compare(policy, shadowInput(),
                Map.of("approved", true), Map.of("approved", true), Set.of(), true, List.of("response-ev"));

        assertEquals(ShadowStatus.REGRESSION, result.status());
        assertTrue(result.differences().contains("SHADOW_WRITE_SIDE_EFFECT_NOT_SAFELY_SUPPRESSED"));
        assertFalse(result.canEnterCanary());
    }

    @Test
    void scenario10_dynamicResponseFieldsCanBeNormalizedDeterministically() {
        SafetyPolicy policy = safeReadPolicy();
        DifferentialResult result = new ShadowTrafficValidator().compare(policy, shadowInput(),
                Map.of("amount", 10, "timestamp", "old", "requestId", "a"),
                Map.of("amount", 10, "timestamp", "new", "requestId", "b"),
                Set.of("timestamp", "requestId"), true, List.of("response-ev"));

        assertEquals(ShadowStatus.EXACT_MATCH, result.status());
        assertTrue(result.canEnterCanary());
    }

    @Test
    void scenario11_shadowExecutionFailureDoesNotChangePrimaryOutcome() {
        DifferentialResult result = new ShadowTrafficValidator().compare(safeReadPolicy(), shadowInput(),
                Map.of("result", "primary-ok"), Map.of(), Set.of(), false, List.of("shadow-error"));

        assertEquals(ShadowStatus.SHADOW_EXECUTION_FAILED, result.status());
        assertTrue(result.primaryResultUnaffected());
        assertFalse(result.canEnterCanary());
    }

    @Test
    void shadowComparatorClassifiesSemanticAndToleranceMatches() {
        ComparisonPolicy comparison = new ComparisonPolicy(
                Set.of(ComparisonMode.NORMALIZED, ComparisonMode.TOLERANCE), Set.of("timestamp"),
                Set.of("status"), Map.of("score", 0.01), Set.of(), false);
        DifferentialResult result = new ShadowTrafficValidator().compare(safeReadPolicy(), shadowInput(),
                Map.of("status", " APPROVED ", "score", 0.80, "timestamp", "old"),
                Map.of("status", "approved", "score", 0.805, "timestamp", "new"),
                comparison, true, List.of("response-ev"));

        assertEquals(ShadowStatus.WITHIN_TOLERANCE, result.status());
        assertTrue(result.differences().contains("SEMANTIC_DIFFERENCE:status"));
        assertTrue(result.differences().contains("WITHIN_TOLERANCE:score"));
        assertTrue(result.canEnterCanary());
    }

    @Test
    void expectedDifferenceRequiresExplicitApprovalBeforeCanaryEligibility() {
        ComparisonPolicy unapproved = new ComparisonPolicy(Set.of(ComparisonMode.DETERMINISTIC), Set.of(),
                Set.of(), Map.of(), Set.of("explanation"), false);
        DifferentialResult held = new ShadowTrafficValidator().compare(safeReadPolicy(), shadowInput(),
                Map.of("explanation", "legacy"), Map.of("explanation", "modern"),
                unapproved, true, List.of("response-ev"));
        assertEquals(ShadowStatus.EXPECTED_DIFFERENCE, held.status());
        assertFalse(held.canEnterCanary());

        ComparisonPolicy approved = new ComparisonPolicy(Set.of(ComparisonMode.DETERMINISTIC), Set.of(),
                Set.of(), Map.of(), Set.of("explanation"), true);
        DifferentialResult eligible = new ShadowTrafficValidator().compare(safeReadPolicy(), shadowInput(),
                Map.of("explanation", "legacy"), Map.of("explanation", "modern"),
                approved, true, List.of("response-ev"));
        assertTrue(eligible.canEnterCanary());
    }

    @Test
    void nondeterministicInputIsExplicitlyNotComparable() {
        ComparisonPolicy comparison = new ComparisonPolicy(Set.of(ComparisonMode.NOT_COMPARABLE), Set.of(),
                Set.of(), Map.of(), Set.of(), false);
        DifferentialResult result = new ShadowTrafficValidator().compare(safeReadPolicy(), shadowInput(),
                Map.of("marketRate", 1.1), Map.of("marketRate", 1.2), comparison, true, List.of("response-ev"));

        assertEquals(ShadowStatus.NOT_COMPARABLE, result.status());
        assertFalse(result.canEnterCanary());
    }

    @Test
    void scenario12_businessMetricFailureRollsBackCanaryDespiteHealthyTechnicalSignals() {
        GateEvidence gates = gates(false, false);
        PromotionDecision result = new ProgressiveTrafficController().evaluate(
                new TrafficStageRequest(Provider.SERVICE_MESH, Stage.CANARY_1, Stage.CANARY_5,
                        Cohort.LOW_RISK_TENANT, gates, false));

        assertEquals(TrafficDecision.ROLLBACK, result.decision());
        assertTrue(result.blockers().contains("BUSINESS_INVARIANT_FAILED"));
        assertEquals(Stage.CANARY_1, result.effectiveStage());
    }

    @Test
    void canaryPromotionCannotSkipStagesEvenWhenAllSignalsPass() {
        PromotionDecision result = new ProgressiveTrafficController().evaluate(
                new TrafficStageRequest(Provider.SERVICE_MESH, Stage.SHADOW_ONLY, Stage.CANARY_25,
                        Cohort.LOW_RISK_TENANT, gates(true, false), false));
        assertEquals(TrafficDecision.HOLD, result.decision());
        assertTrue(result.blockers().contains("TRAFFIC_STAGE_SKIP_OR_REPLAY_FORBIDDEN"));
    }

    @Test
    void cutoverStepRequiresApprovedFrozenManifestEvidence() {
        FrozenManifest manifest = new FrozenManifest("cutover-1", "org-1", "landscape-1", "commits",
                "artifacts", "contract-1", "compatibility", "frontier", "traffic-1", "validation",
                "rollback-1", NOW, List.of(), List.of("manifest-ev"));
        CutoverStep step = new CutoverStep("write", StepType.SWITCH_WRITE, List.of("read-cutover"),
                List.of("data", "business"), RollbackClassification.REVERSIBLE_WITH_DATA_REPAIR,
                true, false, true, List.of("step-ev"));
        StepDecision decision = new SystemCutoverOrchestrator().evaluateStep(
                CompositeState.READ_CUTOVER, manifest, step, true, true);
        assertFalse(decision.allowed());
        assertTrue(decision.blockers().contains("FROZEN_MANIFEST_APPROVAL_MISSING"));
    }

    @Test
    void negativeCdcMetricsAreRejectedInsteadOfPassingLagGates() {
        assertThrows(IllegalArgumentException.class, () -> new CdcStatus("cdc", "source", "target",
                -1, 0, 0, 0, 0, true, true, List.of("evidence")));
    }

    @Test
    void scenario13_readCutoverAndWriteOwnershipAreSeparateGates() {
        DataCutoverResult result = new DataMigrationController().evaluateCutover(cutover(0, false, true));

        assertTrue(result.readCutoverAllowed());
        assertFalse(result.writeCutoverAllowed());
        assertEquals(CutoverDecision.APPROVE_READ, result.decision());
        assertTrue(result.blockers().contains("NEW_WRITE_IDEMPOTENCY_FAILED"));
    }

    @Test
    void scenario14_newWritesUnreadableByLegacyRequireForwardFix() {
        SystemCutoverOrchestrator.RollbackDecision result = new SystemCutoverOrchestrator().rollback(
                new SystemCutoverOrchestrator.RollbackContext(true, false, false,
                        false, false, List.of("rollback-ev")));

        assertEquals(SystemCutoverOrchestrator.RollbackLevel.FORWARD_FIX, result.level());
        assertEquals(RollbackClassification.FORWARD_FIX_ONLY, result.classification());
        assertTrue(result.blockers().contains("LEGACY_CANNOT_READ_NEW_WRITES"));
    }

    @Test
    void scenario15_crossLanguageJourneyBusinessStateOutranksServiceChecks() {
        Journey journey = journey();
        JourneyRunEvidence evidence = new JourneyRunEvidence(true, true, false, 2,
                List.of("m1", "m2"), true, true, true, true, true, true, List.of("run-ev"));
        JourneyDecision result = new BusinessJourneyValidator().validate(journey, evidence);

        assertEquals(ConsistencyStatus.BUSINESS_INVARIANT_FAILED, result.status());
        assertFalse(result.systemGatePassed());
    }

    @Test
    void scenario16_duplicateMessageIsSuppressedByInboxIdempotency() {
        InboxIdempotency inbox = new InboxIdempotency();

        assertEquals(WriteResult.SUCCEEDED, inbox.accept("event-16"));
        assertEquals(WriteResult.DUPLICATE_SUPPRESSED, inbox.accept("event-16"));
        assertEquals(1, inbox.uniqueMessages());
    }

    @Test
    void scenario17_expiredCompatibilityWindowWithUsageCannotClose() {
        CompatibilityWindow window = new CompatibilityWindow("window-17", "org-1", "orders.v1",
                "1.0", "2.0", NOW.minus(Duration.ofDays(30)), NOW.minus(Duration.ofDays(1)), "team-orders",
                List.of(Strategy.MULTI_VERSION_ENDPOINT), List.of("1->2"), 3,
                true, true, true, "remove-old-orders", List.of("usage-ev"));
        WindowDecision result = new CompatibilityGovernance().evaluate(window, NOW, true);

        assertEquals(WindowStatus.EXPIRED_WITH_USAGE, result.status());
        assertFalse(result.contractRemovalAllowed());
    }

    @Test
    void scenario18_legacyBatchAccessBlocksDecommission() {
        SystemCutoverOrchestrator.DecommissionEvidence evidence =
                new SystemCutoverOrchestrator.DecommissionEvidence(true, true, true, false,
                        true, true, true, true, true, true, true, true, true, List.of("decommission-ev"));
        SystemCutoverOrchestrator.DecommissionDecision result =
                new SystemCutoverOrchestrator().decommission(evidence);

        assertFalse(result.allowed());
        assertEquals(CompositeState.LEGACY_DECOMMISSION_BLOCKED, result.state());
        assertTrue(result.blockers().contains("LEGACY_BATCH_ACCESS_PRESENT"));
    }

    private ContractVersion contract(ContractType type, String version, Language producerLanguage,
                                     Map<String, String> fields, Set<String> required,
                                     Map<String, Set<String>> enumValues, Map<String, String> formats) {
        ContractIdentity identity = new ContractIdentity("org-1", "orders", type, "OrderContract", 1);
        return new ContractVersion("contract-" + version, identity, version,
                producerLanguage.name().toLowerCase() + "-producer", ContractStrength.AUTHORITATIVE,
                CompositeIds.hash(type, version, fields), NOW, fields, required, enumValues, formats,
                List.of("contract-evidence-" + version));
    }

    private Consumer consumer(String id, Language language, boolean connected, boolean external) {
        return new Consumer(id, language, connected, external, "1.0.0", "2.0.0", List.of("consumer-ev-" + id));
    }

    private SystemNode node(String id, Language language, NodeType type) {
        return new SystemNode(id, "org-1", type, id, language, "repo-" + id,
                "deploy-" + id, "prod", List.of("node-ev-" + id));
    }

    private DependencyEdge edge(String source, String target, EdgeType type) {
        EdgeEvidence evidence = new EdgeEvidence("edge-ev-" + source + "-" + target,
                EvidenceSource.RUNTIME_TRACE, NOW, "prod", CompositeIds.hash(source, target, type));
        return new DependencyEdge("edge-" + source + "-" + target + "-" + type,
                "org-1", source, target, type, "prod", .95, NOW.minusSeconds(60), NOW,
                3, EdgeValidity.ACTIVE, List.of(evidence), true, "contract:" + source + ":" + target);
    }

    private SystemLandscape landscape(List<SystemNode> nodes, List<DependencyEdge> edges) {
        return new SystemLandscapeService().build(new SystemLandscapeService.BuildRequest(
                "org-1", 0, NOW, nodes, edges, COMPLETE, List.of()));
    }

    private CutoverEvidence cutover(long lag, boolean idempotency, boolean businessApproval) {
        BackfillChunk chunk = new BackfillChunk("chunk-1", "0", "100", "COMPLETED",
                100, 100, "hash", "hash", "checkpoint-100", 0, true);
        CdcStatus cdc = new CdcStatus("cdc-orders", "lsn-200", "lsn-200", lag,
                0, 0, 0, 0, true, true, List.of("cdc-ev"));
        Reconciliation reconciliation = new Reconciliation(true, true, true, true, true,
                List.of(), List.of("reconcile-ev"));
        return new CutoverEvidence(List.of(chunk), cdc, reconciliation, 30,
                true, true, true, idempotency, businessApproval, "lsn-200", ReadMode.NEW_PRIMARY_LEGACY_FALLBACK);
    }

    private SafetyPolicy safeReadPolicy() {
        return new SafetyPolicy(ShadowType.HTTP_MIRROR, false, SideEffectPolicy.SUPPRESS,
                Map.of("email", SensitiveDataAction.HASH), true, true, true, "retention-30d");
    }

    private ShadowInput shadowInput() {
        return new ShadowInput("experiment-13", "request-13", "org-1", "primary-hash",
                "shadow-hash", "transform-v1", "orders-v2", List.of("request-ev"));
    }

    private GateEvidence gates(boolean businessPassed, boolean writeOwnershipChange) {
        return new GateEvidence(true, true, true, true, businessPassed, true, true, true,
                true, true, true, true, false, true, writeOwnershipChange, false, List.of("gate-ev"));
    }

    private Journey journey() {
        return new Journey("checkout", "org-1", List.of(
                new JourneyStep("capture", "java-api", Language.JAVA, "http-v1", "event-v1", List.of("order"), 1000, false),
                new JourneyStep("ledger", "dotnet-ledger", Language.DOTNET, "event-v1", "ledger-v1", List.of("entry"), 1000, false),
                new JourneyStep("risk", "python-risk", Language.PYTHON, "ledger-v1", "risk-v1", List.of(), 1000, true)),
                true, List.of("journey-definition-ev"));
    }
}
