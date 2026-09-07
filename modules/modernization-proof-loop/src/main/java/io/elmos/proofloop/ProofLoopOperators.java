package io.elmos.proofloop;

import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static io.elmos.proofloop.ProofLoopModels.CertificateLevel;
import static io.elmos.proofloop.ProofLoopModels.ExecutionClass;
import static io.elmos.proofloop.ProofLoopModels.ExecutionRequest;
import static io.elmos.proofloop.ProofLoopModels.RunState;

/**
 * Fail-closed domain operators for every Batch 105-108 Skill.
 *
 * <p>The operators only derive decisions from typed inputs and independently verified evidence. Caller supplied
 * booleans named {@code pass}, {@code certified}, {@code destroyed}, or {@code productionReady} are deliberately
 * never read. Side effects remain behind the existing isolated Runner and provider adapters.</p>
 */
public final class ProofLoopOperators {
    public static final Duration DEFAULT_EVIDENCE_MAX_AGE = Duration.ofHours(24);

    public record OperationOutcome(
            RunState state,
            List<String> claims,
            List<String> findings,
            Map<String, Object> payload,
            CertificateLevel certificateLevel
    ) {
        public OperationOutcome {
            ProofLoopModels.required(state, "state");
            claims = List.copyOf(claims);
            findings = List.copyOf(findings);
            payload = Map.copyOf(payload);
            ProofLoopModels.required(certificateLevel, "certificateLevel");
            if (state == RunState.PASSED && !findings.isEmpty()) {
                throw new IllegalArgumentException("passed outcomes cannot retain findings");
            }
        }
    }

    private final Duration maximumEvidenceAge;

    public ProofLoopOperators() {
        this(DEFAULT_EVIDENCE_MAX_AGE);
    }

    public ProofLoopOperators(Duration maximumEvidenceAge) {
        if (maximumEvidenceAge == null || maximumEvidenceAge.isNegative() || maximumEvidenceAge.isZero()) {
            throw new IllegalArgumentException("maximumEvidenceAge must be positive");
        }
        this.maximumEvidenceAge = maximumEvidenceAge;
    }

    public OperationOutcome evaluate(SkillContractCatalog.Contract contract, ExecutionRequest request, Instant now) {
        if (!contract.id().equals(request.skillId())) throw new IllegalArgumentException("request/contract mismatch");

        List<String> findings = new ArrayList<>();
        if (contract.executionClass() == ExecutionClass.ISOLATED_RUNNER) {
            requireVerified(request, "execution:" + contract.id(), now, findings);
        } else if (contract.executionClass() == ExecutionClass.INDEPENDENT_GATE) {
            requireVerified(request, "gate:" + contract.id(), now, findings);
        }

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("contractId", contract.id());
        payload.put("contractDigest", contract.canonicalSha256());
        payload.put("executionClass", contract.executionClass().name());
        payload.put("evaluatedAt", now.toString());

        switch (contract.id()) {
            case "B105-S01" -> selectProject(request, now, findings, payload);
            case "B105-S02" -> freezeBaseline(request, findings, payload);
            case "B105-S03" -> requireEvidenceSet(request, now, findings,
                    "baseline:clean-build", "baseline:test-inventory", "baseline:environment");
            case "B105-S04" -> requireEvidenceSet(request, now, findings, "jdk:matrix", "jdk:jdeps", "jdk:jdeprscan");
            case "B105-S05" -> stagedPlan(request, findings, payload);
            case "B105-S06" -> rewriteBoundary(request, now, findings, payload);
            case "B105-S07" -> attribution(request, findings, payload);
            case "B105-S08" -> failureTaxonomy(request, findings, payload);
            case "B105-S09" -> diagnosticOnly(request, findings, payload);
            case "B105-S10" -> semanticRepair(request, now, findings, payload);
            case "B105-S11" -> manualObligation(request, now, findings, payload);
            case "B105-S12" -> testPreservation(request, findings, payload);
            case "B105-S13" -> matrixVerification(request, now, findings, payload);
            case "B105-S14" -> demoGate(request, now, findings, payload);
            case "B105-S15" -> publication(request, now, findings, payload);
            case "B105-S16" -> routeCertification(request, now, findings, payload);

            case "B106-S01" -> runtimeDetection(request, findings, payload);
            case "B106-S02" -> runtimeManifest(request, findings, payload);
            case "B106-S03" -> manifestValidation(request, findings, payload);
            case "B106-S04", "B106-S05", "B106-S06", "B106-S07" -> languageAdapter(request, findings, payload);
            case "B106-S08" -> ociNormalization(request, now, findings, payload);
            case "B106-S09" -> cacheSnapshot(request, now, findings, payload);
            case "B106-S10" -> sandboxProvision(request, now, findings, payload);
            case "B106-S11" -> endpointExposure(request, now, findings, payload);
            case "B106-S12" -> readinessState(request, findings, payload);
            case "B106-S13" -> readyTriggeredTtl(request, findings, payload);
            case "B106-S14" -> logStream(request, now, findings, payload);
            case "B106-S15" -> cleanup(request, now, findings, payload);
            case "B106-S16" -> providerCertification(request, now, findings, payload);

            case "B107-S01" -> healthProbe(request, now, findings, payload);
            case "B107-S02" -> openApiDiscovery(request, now, findings, payload);
            case "B107-S03" -> openApiGate(request, now, findings, payload);
            case "B107-S04" -> dualReplay(request, now, findings, payload);
            case "B107-S05" -> scenarioSuite(request, findings, payload);
            case "B107-S06" -> newman(request, now, findings, payload);
            case "B107-S07" -> invariantOracle(request, now, findings, payload);
            case "B107-S08" -> routingCompatibility(request, now, findings, payload);
            case "B107-S09" -> browserLaunch(request, now, findings, payload);
            case "B107-S10" -> browserNetworkGate(request, now, findings, payload);
            case "B107-S11" -> semanticAssertions(request, now, findings, payload);
            case "B107-S12" -> screenshots(request, now, findings, payload);
            case "B107-S13" -> frontendDifferential(request, now, findings, payload);
            case "B107-S14" -> streaming(request, now, findings, payload);
            case "B107-S15" -> liveEvidenceBundle(request, now, findings, payload);
            case "B107-S16" -> liveEquivalenceGate(request, now, findings, payload);

            case "B108-S01" -> evidenceWorkspace(request, findings, payload);
            case "B108-S02" -> evidenceLineage(request, now, findings, payload);
            case "B108-S03" -> rewriteEvidence(request, now, findings, payload);
            case "B108-S04" -> agentLedger(request, now, findings, payload);
            case "B108-S05" -> manualLedger(request, now, findings, payload);
            case "B108-S06" -> previewEvidence(request, now, findings, payload);
            case "B108-S07" -> expirationAttestation(request, now, findings, payload);
            case "B108-S08" -> beforeAfterSummary(request, findings, payload);
            case "B108-S09" -> automationRatio(request, findings, payload);
            case "B108-S10" -> riskRegister(request, findings, payload);
            case "B108-S11" -> executiveReport(request, findings, payload);
            case "B108-S12" -> pullRequest(request, now, findings, payload);
            case "B108-S13" -> requiredChecks(request, now, findings, payload);
            case "B108-S14" -> previewAccess(request, now, findings, payload);
            case "B108-S15" -> commercialPackage(request, now, findings, payload);
            case "B108-S16" -> certificateLadder(request, now, findings, payload);
            default -> throw new IllegalArgumentException("unimplemented Skill " + contract.id());
        }

        RunState state = findings.isEmpty() ? RunState.PASSED : RunState.BLOCKED;
        List<String> claims = findings.isEmpty()
                ? List.of("contract_validated", "evidence_bound", "tenant_subject_bound")
                : List.of("contract_validated", "fail_closed");
        CertificateLevel level = certificateLevel(contract.id(), request, now, findings.isEmpty());
        payload.put("decision", state.name());
        payload.put("findings", List.copyOf(findings));
        payload.put("certificateLevel", level.name());
        return new OperationOutcome(state, claims, findings, payload, level);
    }

    private void selectProject(ExecutionRequest request, Instant now, List<String> findings, Map<String, Object> payload) {
        requireVerified(request, "dependency:B104-S16", now, findings);
        if (!bool(request, "licenseAllowed", false)) findings.add("license_policy_not_satisfied");
        if (!bool(request, "hasBuild", false)) findings.add("build_surface_not_detected");
        if (!bool(request, "hasTests", false)) findings.add("test_estate_not_detected");
        if (!bool(request, "hasVisibleService", false)) findings.add("visible_service_not_detected");
        payload.put("selectionScore", longValue(request, "selectionScore", 0));
    }

    private void freezeBaseline(ExecutionRequest request, List<String> findings, Map<String, Object> payload) {
        if (blank(request.subject().baselineCommit())) findings.add("immutable_baseline_commit_missing");
        if (!bool(request, "treeObjectsVerified", false)) findings.add("git_tree_not_verified");
        if (bool(request, "upstreamModified", false)) findings.add("upstream_mutation_forbidden");
        payload.put("baselineCommit", request.subject().baselineCommit());
    }

    private void stagedPlan(ExecutionRequest request, List<String> findings, Map<String, Object> payload) {
        if (!bool(request, "dagAcyclic", false)) findings.add("migration_plan_cycle_detected");
        if (!bool(request, "rollbackPinned", false)) findings.add("rollback_commit_not_pinned");
        if (!bool(request, "includesBridgeStage", false)) findings.add("spring_bridge_stage_missing");
        payload.put("targetSpringBoot", text(request, "targetSpringBoot", "UNSPECIFIED"));
    }

    private void rewriteBoundary(ExecutionRequest request, Instant now, List<String> findings, Map<String, Object> payload) {
        requireEvidenceSet(request, now, findings, "rewrite:dry-run", "rewrite:stage-gate", "rewrite:idempotency");
        if (!bool(request, "recipeDigestPinned", false)) findings.add("recipe_digest_not_pinned");
        if (!bool(request, "singleResponsibilityCommit", false)) findings.add("rewrite_stage_commit_not_atomic");
        payload.put("recipeLock", text(request, "recipeLock", "UNSPECIFIED"));
    }

    private void attribution(ExecutionRequest request, List<String> findings, Map<String, Object> payload) {
        double rule = decimal(request, "ruleShare", -1);
        double agent = decimal(request, "agentShare", -1);
        double manual = decimal(request, "manualShare", -1);
        double unknown = decimal(request, "unknownShare", -1);
        if (rule < 0 || agent < 0 || manual < 0 || unknown < 0) findings.add("attribution_dimensions_missing");
        else if (Math.abs(rule + agent + manual + unknown - 1.0) > 0.000001) findings.add("attribution_not_reconciled");
        if (blank(text(request, "metricDefinitionVersion", ""))) findings.add("metric_definition_version_missing");
        payload.put("conservativeUnknownShare", Math.max(unknown, 0));
    }

    private void failureTaxonomy(ExecutionRequest request, List<String> findings, Map<String, Object> payload) {
        if (longValue(request, "failureCount", -1) < 0) findings.add("failure_inventory_missing");
        if (!bool(request, "logsRedacted", false)) findings.add("diagnostic_logs_not_redacted");
        payload.put("taxonomyVersion", text(request, "taxonomyVersion", "batch105-v1"));
    }

    private void diagnosticOnly(ExecutionRequest request, List<String> findings, Map<String, Object> payload) {
        if (!bool(request, "workspaceReadOnly", false)) findings.add("diagnostic_workspace_not_read_only");
        if (longValue(request, "workspaceDiffBytes", -1) != 0) findings.add("diagnostic_pass_modified_workspace");
        if (bool(request, "writeToolEnabled", false)) findings.add("diagnostic_write_tool_enabled");
        payload.put("mode", "DIAGNOSTIC_ONLY");
    }

    private void semanticRepair(ExecutionRequest request, Instant now, List<String> findings, Map<String, Object> payload) {
        requireEvidenceSet(request, now, findings, "repair:regression-test", "repair:stage-gate");
        long changed = longValue(request, "changedFiles", Long.MAX_VALUE);
        long budget = longValue(request, "maxChangedFiles", -1);
        if (budget < 0 || changed > budget) findings.add("repair_budget_exceeded");
        if (!bool(request, "commitProvenanceRecorded", false)) findings.add("repair_commit_provenance_missing");
        payload.put("changedFiles", changed);
    }

    private void manualObligation(ExecutionRequest request, Instant now, List<String> findings, Map<String, Object> payload) {
        long highRisk = longValue(request, "highRiskFixCount", 0);
        if (highRisk > 0) requireVerified(request, "manual:dual-approval", now, findings);
        if (!bool(request, "manualFixesLinkedToTests", false)) findings.add("manual_fix_regression_link_missing");
        payload.put("highRiskFixCount", highRisk);
    }

    private void testPreservation(ExecutionRequest request, List<String> findings, Map<String, Object> payload) {
        long before = longValue(request, "testsBefore", -1);
        long after = longValue(request, "testsAfter", -1);
        long skippedBefore = longValue(request, "skippedBefore", -1);
        long skippedAfter = longValue(request, "skippedAfter", -1);
        double coverageBefore = decimal(request, "coverageBefore", -1);
        double coverageAfter = decimal(request, "coverageAfter", -1);
        if (before < 0 || after < 0 || skippedBefore < 0 || skippedAfter < 0 || coverageBefore < 0 || coverageAfter < 0) {
            findings.add("test_metrics_incomplete");
        } else {
            if (after < before && !bool(request, "testRemovalApproved", false)) findings.add("tests_removed_without_approval");
            if (skippedAfter > skippedBefore) findings.add("skipped_test_count_increased");
            if (coverageAfter + 0.000001 < coverageBefore && !bool(request, "coverageRegressionApproved", false)) {
                findings.add("coverage_regressed");
            }
        }
        if (bool(request, "testsWeakened", false)) findings.add("test_expectations_weakened");
        payload.put("testsBefore", before);
        payload.put("testsAfter", after);
    }

    private void matrixVerification(ExecutionRequest request, Instant now, List<String> findings, Map<String, Object> payload) {
        requireVerified(request, "matrix:results", now, findings);
        long required = longValue(request, "requiredCells", -1);
        long passed = longValue(request, "passedCells", -1);
        long failed = longValue(request, "failedCells", 0);
        long notRun = longValue(request, "notRunCells", 0);
        if (required < 1 || passed != required || failed > 0 || notRun > 0) findings.add("profile_database_matrix_incomplete");
        payload.put("matrix", Map.of("required", required, "passed", passed, "failed", failed, "notRun", notRun));
    }

    private void demoGate(ExecutionRequest request, Instant now, List<String> findings, Map<String, Object> payload) {
        requireEvidenceSet(request, now, findings, "gate:baseline-reproducible", "gate:test-preservation", "gate:matrix");
        if (longValue(request, "blockingFindings", 1) != 0) findings.add("demo_gate_has_blocking_findings");
        payload.put("maximumDecision", findings.isEmpty() ? "DEMO_READY" : "PARTIAL");
    }

    private void publication(ExecutionRequest request, Instant now, List<String> findings, Map<String, Object> payload) {
        requireEvidenceSet(request, now, findings, "journey:sanitized", "journey:replay");
        if (!bool(request, "visibilityControlled", false)) findings.add("catalog_visibility_not_controlled");
        payload.put("publicationState", findings.isEmpty() ? "ACTIVE" : "BLOCKED");
    }

    private void routeCertification(ExecutionRequest request, Instant now, List<String> findings, Map<String, Object> payload) {
        requireEvidenceSet(request, now, findings, "route:independent-replay", "route:negative-candidates", "route:benchmark");
        payload.put("maximumDecision", findings.isEmpty() ? "CUSTOMER_READY" : "PARTIAL");
    }

    private void runtimeDetection(ExecutionRequest request, List<String> findings, Map<String, Object> payload) {
        List<?> candidates = list(request, "serviceCandidates");
        if (candidates.isEmpty()) findings.add("no_runtime_service_candidate");
        if (candidates.size() > 1 && blank(text(request, "selectedService", ""))) findings.add("ambiguous_primary_service");
        if (bool(request, "untrustedCodeExecuted", false)) findings.add("detection_executed_untrusted_code");
        payload.put("candidateCount", candidates.size());
    }

    private void runtimeManifest(ExecutionRequest request, List<String> findings, Map<String, Object> payload) {
        List<?> buildArgv = list(request, "buildArgv");
        List<?> startArgv = list(request, "startArgv");
        if (buildArgv.isEmpty() || startArgv.isEmpty()) findings.add("runtime_commands_must_be_nonempty_argv");
        if (request.inputs().containsKey("buildCommand") || request.inputs().containsKey("startCommand")) findings.add("shell_string_commands_forbidden");
        long ttl = longValue(request, "ttlSeconds", -1);
        if (ttl < 1 || ttl > 600) findings.add("preview_ttl_outside_1_600_seconds");
        if (!"0.0.0.0".equals(text(request, "bindHost", ""))) findings.add("runtime_not_bound_to_sandbox_interface");
        payload.put("ttlSeconds", ttl);
    }

    private void manifestValidation(ExecutionRequest request, List<String> findings, Map<String, Object> payload) {
        if (!bool(request, "schemaValid", false)) findings.add("runtime_manifest_schema_invalid");
        if (!bool(request, "providerCapabilitiesSatisfied", false)) findings.add("provider_capability_mismatch");
        if (bool(request, "broadEgress", false)) findings.add("broad_network_egress_forbidden");
        if (bool(request, "secretLiteralPresent", false)) findings.add("literal_secret_forbidden");
        payload.put("normalized", findings.isEmpty());
    }

    private void languageAdapter(ExecutionRequest request, List<String> findings, Map<String, Object> payload) {
        if (blank(text(request, "toolchainVersion", ""))) findings.add("toolchain_version_missing");
        if (blank(text(request, "builderImageDigest", ""))) findings.add("builder_image_digest_missing");
        if (!bool(request, "entrypointUnique", false)) findings.add("runtime_entrypoint_not_unique");
        if (!bool(request, "lockfilePreserved", false)) findings.add("customer_dependency_lock_not_preserved");
        payload.put("adapter", text(request, "adapter", "UNSPECIFIED"));
    }

    private void ociNormalization(ExecutionRequest request, Instant now, List<String> findings, Map<String, Object> payload) {
        requireEvidenceSet(request, now, findings, "oci:build", "oci:sbom", "oci:provenance", "oci:scan");
        if (blank(request.subject().imageDigest())) findings.add("digest_pinned_oci_image_missing");
        if (bool(request, "secretLeakDetected", true)) findings.add("oci_layer_secret_scan_not_clean");
        payload.put("imageDigest", request.subject().imageDigest());
    }

    private void cacheSnapshot(ExecutionRequest request, Instant now, List<String> findings, Map<String, Object> payload) {
        requireEvidenceSet(request, now, findings, "cache:snapshot-signature", "cache:sanitization");
        if (bool(request, "containsCustomerSource", true)) findings.add("cache_snapshot_contains_customer_source");
        if (bool(request, "containsCredential", true)) findings.add("cache_snapshot_contains_credentials");
        payload.put("cacheScope", text(request, "cacheScope", "TENANT_PRIVATE"));
    }

    private void sandboxProvision(ExecutionRequest request, Instant now, List<String> findings, Map<String, Object> payload) {
        requireEvidenceSet(request, now, findings, "sandbox:image-signature", "sandbox:policy", "sandbox:provider-receipt");
        if (!bool(request, "readOnlyRoot", false)) findings.add("sandbox_root_not_read_only");
        if (!bool(request, "metadataBlocked", false)) findings.add("cloud_metadata_not_blocked");
        if (!bool(request, "tenantQuotaReserved", false)) findings.add("tenant_quota_not_reserved");
        if (!bool(request, "shortLivedIdentity", false)) findings.add("short_lived_workload_identity_missing");
        payload.put("isolation", "PER_RUN");
    }

    private void endpointExposure(ExecutionRequest request, Instant now, List<String> findings, Map<String, Object> payload) {
        requireVerified(request, "endpoint:route-receipt", now, findings);
        if (!bool(request, "portDeclared", false)) findings.add("undeclared_port_exposure");
        if (!bool(request, "tlsEnabled", false)) findings.add("preview_tls_required");
        if (!bool(request, "accessPolicyApplied", false)) findings.add("preview_access_policy_missing");
        if (bool(request, "internalTopologyExposed", false)) findings.add("internal_topology_disclosure");
        payload.put("endpointStoredAsHash", true);
    }

    private void readinessState(ExecutionRequest request, List<String> findings, Map<String, Object> payload) {
        String state = text(request, "runtimeState", "UNKNOWN");
        if (!Set.of("READY", "BUILD_FAILED", "START_FAILED", "HEALTH_FAILED", "POLICY_BLOCKED").contains(state)) {
            findings.add("runtime_state_not_terminal_or_ready");
        }
        if ("READY".equals(state) && !bool(request, "readinessProbePassed", false)) findings.add("ready_without_probe_evidence");
        if (!bool(request, "replayReceiptVerified", false)) findings.add("workflow_replay_receipt_missing");
        payload.put("runtimeState", state);
    }

    private void readyTriggeredTtl(ExecutionRequest request, List<String> findings, Map<String, Object> payload) {
        Instant readyAt = instant(request, "readyAt");
        Instant expiresAt = instant(request, "expiresAt");
        Instant createdAt = instant(request, "createdAt");
        long ttl = longValue(request, "ttlSeconds", -1);
        if (readyAt == null || expiresAt == null) findings.add("ready_or_expiration_timestamp_missing");
        else {
            if (createdAt != null && readyAt.isBefore(createdAt)) findings.add("ready_timestamp_precedes_creation");
            if (!expiresAt.equals(readyAt.plusSeconds(ttl))) findings.add("ttl_not_anchored_to_ready_timestamp");
        }
        if (ttl < 1 || ttl > 600) findings.add("ttl_outside_1_600_seconds");
        payload.put("ttlStartsAt", "READY");
    }

    private void logStream(ExecutionRequest request, Instant now, List<String> findings, Map<String, Object> payload) {
        requireEvidenceSet(request, now, findings, "logs:hash-chain", "logs:redaction");
        if (!bool(request, "monotonicSequence", false)) findings.add("log_sequence_not_monotonic");
        if (!bool(request, "streamClosedAtTerminal", false)) findings.add("terminal_log_stream_not_closed");
        payload.put("resumableByCursor", bool(request, "cursorResumeVerified", false));
    }

    private void cleanup(ExecutionRequest request, Instant now, List<String> findings, Map<String, Object> payload) {
        requireEvidenceSet(request, now, findings, "cleanup:route-revocation", "cleanup:provider-destroy",
                "cleanup:secret-revocation", "cleanup:orphan-recheck", "cleanup:cost-finalization");
        Instant routeRevokedAt = instant(request, "routeRevokedAt");
        Instant destroyedAt = instant(request, "instanceDestroyedAt");
        if (routeRevokedAt == null || destroyedAt == null || routeRevokedAt.isAfter(destroyedAt)) {
            findings.add("cleanup_order_must_revoke_route_before_destroy");
        }
        if (!bool(request, "temporaryVolumesDeleted", false)) findings.add("temporary_volumes_not_deleted");
        if (longValue(request, "orphanCount", -1) != 0) findings.add("provider_orphans_remain");
        payload.put("cleanupState", findings.isEmpty() ? "CLEAN" : "CLEANUP_FAILED");
    }

    private void providerCertification(ExecutionRequest request, Instant now, List<String> findings, Map<String, Object> payload) {
        requireEvidenceSet(request, now, findings, "provider:contract-tests", "provider:failure-injection", "provider:idempotency");
        if (!bool(request, "allMandatoryCapabilities", false)) findings.add("provider_mandatory_capability_missing");
        if (bool(request, "silentCapabilityDowngrade", true)) findings.add("provider_silent_downgrade_forbidden");
        payload.put("productionRoutable", findings.isEmpty());
    }

    private void healthProbe(ExecutionRequest request, Instant now, List<String> findings, Map<String, Object> payload) {
        requireEvidenceSet(request, now, findings, "probe:inside", "probe:outside");
        if (!bool(request, "statusAssertionPassed", false)) findings.add("health_status_assertion_failed");
        if (longValue(request, "responseBytes", Long.MAX_VALUE) > longValue(request, "maxResponseBytes", -1)) {
            findings.add("health_response_size_limit_exceeded");
        }
        payload.put("probeDecision", findings.isEmpty() ? "PASS" : "UNKNOWN");
    }

    private void openApiDiscovery(ExecutionRequest request, Instant now, List<String> findings, Map<String, Object> payload) {
        requireVerified(request, "openapi:runtime-fetch", now, findings);
        if (!bool(request, "specSchemaValid", false)) findings.add("runtime_openapi_invalid");
        if (bool(request, "unboundedRedirect", false)) findings.add("openapi_redirect_policy_violated");
        payload.put("serversNormalized", true);
    }

    private void openApiGate(ExecutionRequest request, Instant now, List<String> findings, Map<String, Object> payload) {
        requireVerified(request, "openapi:independent-diff", now, findings);
        if (longValue(request, "breakingErrors", 1) > 0) findings.add("openapi_breaking_errors_present");
        if (longValue(request, "policyWarnings", 1) > 0) findings.add("openapi_policy_warnings_present");
        if (bool(request, "expiredAllowlistUsed", false)) findings.add("expired_api_allowlist_entry");
        payload.put("apiCompatible", findings.isEmpty());
    }

    private void dualReplay(ExecutionRequest request, Instant now, List<String> findings, Map<String, Object> payload) {
        requireEvidenceSet(request, now, findings, "replay:baseline", "replay:candidate", "replay:state-observation");
        if (longValue(request, "unknownComparisons", 1) > 0) findings.add("dual_replay_contains_unknown_comparisons");
        if (longValue(request, "semanticDeltas", 1) > 0) findings.add("dual_replay_semantic_delta");
        payload.put("isolatedDatasets", bool(request, "isolatedDatasets", false));
    }

    private void scenarioSuite(ExecutionRequest request, List<String> findings, Map<String, Object> payload) {
        if (longValue(request, "operationCount", -1) < 1) findings.add("openapi_operation_inventory_empty");
        if (!bool(request, "highRiskWritesReviewed", false)) findings.add("high_risk_write_scenarios_not_reviewed");
        if (!bool(request, "authBoundariesCovered", false)) findings.add("authorization_scenarios_missing");
        payload.put("riskOrdered", true);
    }

    private void newman(ExecutionRequest request, Instant now, List<String> findings, Map<String, Object> payload) {
        requireEvidenceSet(request, now, findings, "newman:baseline", "newman:candidate");
        if (longValue(request, "candidateFailures", 1) > 0) findings.add("candidate_newman_failures_present");
        if (!bool(request, "collectionScriptsPolicyValid", false)) findings.add("collection_script_policy_invalid");
        payload.put("toolVersion", text(request, "newmanVersion", "UNSPECIFIED"));
    }

    private void invariantOracle(ExecutionRequest request, Instant now, List<String> findings, Map<String, Object> payload) {
        requireEvidenceSet(request, now, findings, "invariant:baseline", "invariant:candidate", "invariant:cleanup");
        if (longValue(request, "failedInvariants", 1) > 0) findings.add("business_invariant_failed");
        if (longValue(request, "unknownInvariants", 1) > 0) findings.add("business_invariant_unknown");
        payload.put("counterexamplesMinimized", bool(request, "counterexamplesMinimized", false));
    }

    private void routingCompatibility(ExecutionRequest request, Instant now, List<String> findings, Map<String, Object> payload) {
        requireVerified(request, "routing:variant-probes", now, findings);
        if (longValue(request, "unexpectedDeltas", 1) > 0) findings.add("routing_compatibility_delta");
        if (!bool(request, "corsCompared", false)) findings.add("cors_behavior_not_compared");
        payload.put("trailingSlashCovered", bool(request, "trailingSlashCovered", false));
    }

    private void browserLaunch(ExecutionRequest request, Instant now, List<String> findings, Map<String, Object> payload) {
        requireVerified(request, "browser:session", now, findings);
        if (!bool(request, "isolatedProfile", false)) findings.add("browser_profile_not_isolated");
        if (!bool(request, "storageCleaned", false)) findings.add("browser_storage_not_cleaned");
        if (bool(request, "realExternalAccountUsed", false)) findings.add("real_external_account_forbidden");
        payload.put("browserProfile", text(request, "browserProfile", "UNSPECIFIED"));
    }

    private void browserNetworkGate(ExecutionRequest request, Instant now, List<String> findings, Map<String, Object> payload) {
        requireVerified(request, "browser:console-network", now, findings);
        if (longValue(request, "unallowlistedErrors", 1) > 0) findings.add("browser_console_or_network_errors");
        if (bool(request, "rawEventsDiscarded", false)) findings.add("raw_browser_events_discarded");
        payload.put("gate", findings.isEmpty() ? "PASS" : "FAIL");
    }

    private void semanticAssertions(ExecutionRequest request, Instant now, List<String> findings, Map<String, Object> payload) {
        requireVerified(request, "browser:semantic-assertions", now, findings);
        if (longValue(request, "failedAssertions", 1) > 0) findings.add("page_semantic_assertion_failed");
        if (!bool(request, "roleNameLocators", false)) findings.add("semantic_locator_contract_not_met");
        payload.put("accessibilitySnapshotsPresent", bool(request, "accessibilitySnapshotsPresent", false));
    }

    private void screenshots(ExecutionRequest request, Instant now, List<String> findings, Map<String, Object> payload) {
        requireVerified(request, "browser:screenshots", now, findings);
        if (!bool(request, "desktopCaptured", false) || !bool(request, "mobileCaptured", false)) findings.add("required_viewports_missing");
        if (!bool(request, "maskingPolicyApplied", false)) findings.add("screenshot_masking_policy_missing");
        payload.put("contentAddressed", true);
    }

    private void frontendDifferential(ExecutionRequest request, Instant now, List<String> findings, Map<String, Object> payload) {
        requireVerified(request, "frontend:independent-diff", now, findings);
        if (longValue(request, "breakingSemanticDeltas", 1) > 0) findings.add("frontend_breaking_semantic_delta");
        if (longValue(request, "unapprovedVisualDeltas", 1) > 0) findings.add("frontend_unapproved_visual_delta");
        payload.put("journeyAligned", bool(request, "journeyAligned", false));
    }

    private void streaming(ExecutionRequest request, Instant now, List<String> findings, Map<String, Object> payload) {
        if (!bool(request, "streamingDeclared", false)) {
            payload.put("decision", "NOT_APPLICABLE");
            return;
        }
        requireVerified(request, "streaming:protocol-run", now, findings);
        if (!bool(request, "resourceReleaseConfirmed", false)) findings.add("streaming_resource_release_not_confirmed");
        if (longValue(request, "semanticDeltas", 1) > 0) findings.add("streaming_semantic_delta");
    }

    private void liveEvidenceBundle(ExecutionRequest request, Instant now, List<String> findings, Map<String, Object> payload) {
        requireEvidenceSet(request, now, findings, "bundle:hashes", "bundle:signature", "bundle:lineage");
        if (longValue(request, "missingEvidence", 1) > 0) findings.add("live_validation_evidence_missing");
        if (longValue(request, "unknownEvidence", 1) > 0) findings.add("live_validation_evidence_unknown");
        payload.put("subjectImage", request.subject().imageDigest());
    }

    private void liveEquivalenceGate(ExecutionRequest request, Instant now, List<String> findings, Map<String, Object> payload) {
        requireEvidenceSet(request, now, findings, "live:health", "live:api", "live:business", "live:browser");
        if (bool(request, "streamingDeclared", false)) requireVerified(request, "live:streaming", now, findings);
        if (longValue(request, "blockingFindings", 1) > 0) findings.add("live_service_blocking_findings");
        payload.put("maximumDecision", findings.isEmpty() ? "RUNTIME_VERIFIED" : "PARTIAL");
    }

    private void evidenceWorkspace(ExecutionRequest request, List<String> findings, Map<String, Object> payload) {
        if (!bool(request, "contentAddressed", false)) findings.add("evidence_workspace_not_content_addressed");
        if (!bool(request, "writerPermissionsScoped", false)) findings.add("evidence_writer_permissions_not_scoped");
        if (longValue(request, "retentionDays", -1) < 1) findings.add("evidence_retention_policy_missing");
        payload.put("tenant", request.subject().organizationId());
    }

    private void evidenceLineage(ExecutionRequest request, Instant now, List<String> findings, Map<String, Object> payload) {
        requireVerified(request, "lineage:validation", now, findings);
        if (longValue(request, "brokenEdges", 1) > 0) findings.add("evidence_lineage_broken");
        if (longValue(request, "subjectMismatches", 1) > 0) findings.add("evidence_subject_mismatch");
        if (bool(request, "lineageCycle", true)) findings.add("evidence_lineage_cycle");
        payload.put("lineageValid", findings.isEmpty());
    }

    private void rewriteEvidence(ExecutionRequest request, Instant now, List<String> findings, Map<String, Object> payload) {
        requireEvidenceSet(request, now, findings, "rewrite:commit", "rewrite:recipe-lock", "rewrite:datatables");
        if (!bool(request, "idempotencyLinked", false)) findings.add("rewrite_idempotency_evidence_missing");
        payload.put("contentAddressed", true);
    }

    private void agentLedger(ExecutionRequest request, Instant now, List<String> findings, Map<String, Object> payload) {
        requireEvidenceSet(request, now, findings, "agent:commit", "agent:tool-transcript", "agent:review");
        if (!bool(request, "patchesLinkedToRootCauses", false)) findings.add("agent_patch_root_cause_link_missing");
        if (decimal(request, "agentCost", -1) < 0) findings.add("agent_cost_not_reconciled");
        payload.put("modelConfigDigestOnly", true);
    }

    private void manualLedger(ExecutionRequest request, Instant now, List<String> findings, Map<String, Object> payload) {
        requireVerified(request, "manual:patch-digests", now, findings);
        if (longValue(request, "expiredApprovals", 1) > 0) findings.add("manual_approval_expired");
        if (longValue(request, "staleApprovals", 1) > 0) findings.add("manual_approval_invalidated_by_code_change");
        payload.put("exceptionsExpiring", true);
    }

    private void previewEvidence(ExecutionRequest request, Instant now, List<String> findings, Map<String, Object> payload) {
        requireEvidenceSet(request, now, findings, "preview:lifecycle", "preview:signature", "preview:schema");
        if (!bool(request, "endpointStoredAsHash", false)) findings.add("raw_preview_endpoint_persisted");
        payload.put("providerSummaryOnly", true);
    }

    private void expirationAttestation(ExecutionRequest request, Instant now, List<String> findings, Map<String, Object> payload) {
        requireEvidenceSet(request, now, findings, "expiration:route-recheck", "expiration:provider-inventory", "expiration:cost-stop");
        if (longValue(request, "orphanCount", -1) != 0) findings.add("expiration_orphans_detected");
        if (!bool(request, "secretsRevoked", false)) findings.add("expiration_secret_revocation_missing");
        payload.put("attestation", findings.isEmpty() ? "PASS" : "FAIL");
    }

    private void beforeAfterSummary(ExecutionRequest request, List<String> findings, Map<String, Object> payload) {
        if (!bool(request, "metricDefinitionsMatch", false)) findings.add("before_after_metric_definition_mismatch");
        if (longValue(request, "unknownMetrics", 1) > 0) findings.add("before_after_metrics_unknown");
        payload.put("sourceMetricsOnly", true);
    }

    private void automationRatio(ExecutionRequest request, List<String> findings, Map<String, Object> payload) {
        double rule = decimal(request, "ruleShare", -1);
        double agent = decimal(request, "agentShare", -1);
        double manual = decimal(request, "manualShare", -1);
        double unknown = decimal(request, "unknownShare", -1);
        if (rule < 0 || agent < 0 || manual < 0 || unknown < 0 || Math.abs(rule + agent + manual + unknown - 1) > .000001) {
            findings.add("automation_ratio_not_reconciled");
        }
        if (!bool(request, "ledgersReconciled", false)) findings.add("automation_ledgers_not_reconciled");
        payload.put("unknownUsesConservativeDenominator", true);
    }

    private void riskRegister(ExecutionRequest request, List<String> findings, Map<String, Object> payload) {
        if (!bool(request, "unknownsIncluded", false)) findings.add("unknown_scope_omitted_from_risk_register");
        if (longValue(request, "unownedRisks", 1) > 0) findings.add("risk_without_owner");
        if (longValue(request, "unapprovedAcceptances", 1) > 0) findings.add("risk_acceptance_not_approved");
        payload.put("riskModel", "impact-likelihood-detectability-v1");
    }

    private void executiveReport(ExecutionRequest request, List<String> findings, Map<String, Object> payload) {
        if (!bool(request, "allNumbersEvidenceLinked", false)) findings.add("executive_report_number_without_evidence");
        if (!bool(request, "residualRisksIncluded", false)) findings.add("executive_report_omits_residual_risk");
        if (bool(request, "modelGeneratedMetric", false)) findings.add("model_generated_metric_forbidden");
        payload.put("recommendationEvidenceBound", true);
    }

    private void pullRequest(ExecutionRequest request, Instant now, List<String> findings, Map<String, Object> payload) {
        requireVerified(request, "scm:draft-pr-readback", now, findings);
        if (!bool(request, "draft", false)) findings.add("evidence_pr_must_start_as_draft");
        if (!bool(request, "headShaMatches", false)) findings.add("pull_request_head_sha_mismatch");
        if (bool(request, "sensitiveUrlEmbedded", false)) findings.add("sensitive_preview_url_in_pr");
        payload.put("scmMutationAuthorized", true);
    }

    private void requiredChecks(ExecutionRequest request, Instant now, List<String> findings, Map<String, Object> payload) {
        requireVerified(request, "scm:protection-readback", now, findings);
        if (!bool(request, "explicitApplyApproval", false)) findings.add("branch_protection_apply_not_approved");
        if (bool(request, "adminBypassEnabled", true)) findings.add("required_checks_admin_bypass_enabled");
        if (longValue(request, "unmappedChecks", 1) > 0) findings.add("required_check_without_unique_gate");
        payload.put("configurationReadBack", true);
    }

    private void previewAccess(ExecutionRequest request, Instant now, List<String> findings, Map<String, Object> payload) {
        requireVerified(request, "access:authorization-decision", now, findings);
        long ttl = longValue(request, "accessTtlSeconds", -1);
        if (ttl < 1 || ttl > 600) findings.add("preview_access_ttl_invalid");
        if (!bool(request, "pathAndMethodScoped", false)) findings.add("preview_access_token_not_scoped");
        if (!bool(request, "revocationHookRegistered", false)) findings.add("preview_access_revocation_hook_missing");
        payload.put("requestContentMinimized", true);
    }

    private void commercialPackage(ExecutionRequest request, Instant now, List<String> findings, Map<String, Object> payload) {
        requireEvidenceSet(request, now, findings, "package:sanitization", "package:signature", "package:customer-index");
        if (!bool(request, "expiredPreviewUsesRestartEntry", false)) findings.add("commercial_package_contains_dead_preview_link");
        if (!bool(request, "scopeAndAssumptionsIncluded", false)) findings.add("commercial_package_scope_missing");
        payload.put("customerViews", List.of("EXECUTIVE", "TECHNICAL"));
    }

    private void certificateLadder(ExecutionRequest request, Instant now, List<String> findings, Map<String, Object> payload) {
        CertificateLevel requested = certificate(request, "requestedCertificateLevel", CertificateLevel.NONE);
        CertificateLevel achieved = CertificateLevel.NONE;
        for (CertificateLevel level : CertificateLevel.values()) {
            if (level == CertificateLevel.NONE) continue;
            if (level.ordinal() > requested.ordinal()) break;
            String key = "certificate:" + level.name();
            if (!verified(request, key, now)) {
                findings.add("certificate_prerequisite_missing:" + level.name());
                break;
            }
            achieved = level;
        }
        if (achieved.ordinal() < requested.ordinal()) findings.add("certificate_level_jump_rejected");
        if (requested.ordinal() >= CertificateLevel.RUNTIME_VERIFIED.ordinal()
                && !verified(request, "certificate:CLEANUP_ATTESTED", now)) {
            findings.add("runtime_certificate_requires_cleanup_attestation");
        }
        if (requested == CertificateLevel.PRODUCTION_CANDIDATE) {
            payload.put("productionApproved", false);
            payload.put("deployAuthorized", false);
        }
        payload.put("requestedLevel", requested.name());
        payload.put("achievedLevel", achieved.name());
    }

    private CertificateLevel certificateLevel(String id, ExecutionRequest request, Instant now, boolean passed) {
        if (!passed) return CertificateLevel.NONE;
        if (id.equals("B108-S16")) {
            CertificateLevel requested = certificate(request, "requestedCertificateLevel", CertificateLevel.NONE);
            for (CertificateLevel level : CertificateLevel.values()) {
                if (level == CertificateLevel.NONE || level.ordinal() > requested.ordinal()) break;
                if (!verified(request, "certificate:" + level.name(), now)) return CertificateLevel.values()[level.ordinal() - 1];
            }
            return requested;
        }
        // Intermediate Skills emit scoped claims, not global certificate levels.
        // Only B108-S16 may advance the ordered certificate ladder.
        return CertificateLevel.NONE;
    }

    private void requireEvidenceSet(ExecutionRequest request, Instant now, List<String> findings, String... keys) {
        for (String key : keys) requireVerified(request, key, now, findings);
    }

    private void requireVerified(ExecutionRequest request, String key, Instant now, List<String> findings) {
        if (!verified(request, key, now)) findings.add("verified_evidence_missing:" + key);
    }

    private boolean verified(ExecutionRequest request, String key, Instant now) {
        ProofLoopModels.EvidenceAssertion evidence = request.evidence().get(key);
        return evidence != null && evidence.independentlyVerified(now, maximumEvidenceAge.toSeconds());
    }

    private static boolean bool(ExecutionRequest request, String key, boolean fallback) {
        Object value = request.inputs().get(key);
        return value instanceof Boolean bool ? bool : fallback;
    }

    private static long longValue(ExecutionRequest request, String key, long fallback) {
        Object value = request.inputs().get(key);
        return value instanceof Number number ? number.longValue() : fallback;
    }

    private static double decimal(ExecutionRequest request, String key, double fallback) {
        Object value = request.inputs().get(key);
        return value instanceof Number number ? number.doubleValue() : fallback;
    }

    private static String text(ExecutionRequest request, String key, String fallback) {
        Object value = request.inputs().get(key);
        return value instanceof String string ? string : fallback;
    }

    private static List<?> list(ExecutionRequest request, String key) {
        Object value = request.inputs().get(key);
        return value instanceof List<?> list ? list : List.of();
    }

    private static Instant instant(ExecutionRequest request, String key) {
        Object value = request.inputs().get(key);
        if (value instanceof Instant instant) return instant;
        if (value instanceof String text) {
            try { return Instant.parse(text); } catch (RuntimeException ignored) { return null; }
        }
        return null;
    }

    private static CertificateLevel certificate(ExecutionRequest request, String key, CertificateLevel fallback) {
        try { return CertificateLevel.valueOf(text(request, key, fallback.name())); }
        catch (IllegalArgumentException ignored) { return fallback; }
    }

    private static boolean blank(String value) { return value == null || value.isBlank(); }
}
