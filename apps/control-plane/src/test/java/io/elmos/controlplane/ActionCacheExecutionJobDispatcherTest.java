package io.elmos.controlplane;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import io.elmos.cas.ActionCache;
import io.elmos.cas.ActionCacheIndex;
import io.elmos.cas.ActionKey;
import io.elmos.cas.ActionKeyBuilder;
import io.elmos.cas.ActionResultRecord;
import io.elmos.cas.CasAccessPolicy;
import io.elmos.cas.CasDigest;
import io.elmos.cas.CasMetrics;
import io.elmos.cas.CasObjectModel;
import io.elmos.cas.CasTelemetry;
import io.elmos.cas.InMemoryActionCacheIndex;
import io.elmos.cas.InMemoryCasStore;
import io.elmos.cas.TenantCasStore;
import io.elmos.workflow.ExecutionJobPort;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import java.math.BigDecimal;
import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

class ActionCacheExecutionJobDispatcherTest {

    private static final String IMAGE =
            "registry.internal/elmos/java21@sha256:" + "a".repeat(64);
    private static final String SOURCE_REF = "cas:sha256:" + "b".repeat(64);

    @Test void aTrustedCacheHitShortCircuitsTheDurableQueue() {
        Fixture fixture = new Fixture(currentTrust());
        fixture.store();
        ExecutionJobPort jobs = mock(ExecutionJobPort.class);
        List<ActionCacheExecutionJobDispatcher.Operation> operations = new ArrayList<>();
        ActionCacheExecutionJobDispatcher dispatcher = fixture.dispatcher(
                jobs, (request, operation) -> {
                    operations.add(operation);
                    return allow(request, operation);
                });

        ActionCacheExecutionJobDispatcher.Outcome outcome =
                dispatcher.dispatch(fixture.request(fixture.reader("tenant-a"),
                        ActionCacheExecutionJobDispatcher.Mode.CACHE_OR_ENQUEUE));

        assertEquals(ActionCacheExecutionJobDispatcher.OutcomeKind.CACHE_HIT, outcome.kind());
        assertTrue(outcome.cacheResultSucceeded());
        assertEquals(List.of(ActionCacheExecutionJobDispatcher.Operation.CACHE_READ), operations);
        assertTrue(outcome.jobId().isEmpty());
        assertTrue(outcome.requestDigest().isEmpty());
        verifyNoInteractions(jobs);
    }

    @Test void anAuthorizedMissEnqueuesAnExactlyBoundTenantJob() {
        Fixture fixture = new Fixture(currentTrust());
        ExecutionJobPort jobs = mock(ExecutionJobPort.class);
        when(jobs.enqueue(any())).thenAnswer(invocation ->
                invocation.<ExecutionJobPort.EnqueueCommand>getArgument(0).jobId());
        List<ActionCacheExecutionJobDispatcher.Operation> operations = new ArrayList<>();
        ActionCacheExecutionJobDispatcher dispatcher = fixture.dispatcher(
                jobs, (request, operation) -> {
                    operations.add(operation);
                    return allow(request, operation);
                });

        ActionCacheExecutionJobDispatcher.Outcome outcome =
                dispatcher.dispatch(fixture.request(fixture.reader("tenant-a"),
                        ActionCacheExecutionJobDispatcher.Mode.CACHE_OR_ENQUEUE));

        assertEquals(ActionCacheExecutionJobDispatcher.OutcomeKind.DURABLE_JOB_ACCEPTED,
                outcome.kind());
        assertFalse(outcome.idempotentReplay());
        assertEquals("DURABLE_JOB_ENQUEUED", outcome.reason());
        assertEquals(List.of(ActionCacheExecutionJobDispatcher.Operation.CACHE_READ,
                ActionCacheExecutionJobDispatcher.Operation.EXECUTE), operations);

        ArgumentCaptor<ExecutionJobPort.EnqueueCommand> command =
                ArgumentCaptor.forClass(ExecutionJobPort.EnqueueCommand.class);
        verify(jobs).enqueue(command.capture());
        ExecutionJobPort.EnqueueCommand persisted = command.getValue();
        assertEquals("tenant-a", persisted.organizationId());
        assertEquals("actor-a", persisted.actorId());
        assertEquals("action-cache:test-1", persisted.idempotencyKey());
        assertEquals(IMAGE, persisted.runnerImage());
        assertEquals((short) 1, persisted.maxAttempts());
        assertEquals(outcome.requestDigest().orElseThrow().hex(), persisted.requestDigest());
        assertEquals(SOURCE_REF, persisted.requestPayload().get("sourceRef"));
        Map<?, ?> binding = (Map<?, ?>) persisted.requestPayload().get("_elmosActionCache");
        assertEquals("1.0", binding.get("schemaVersion"));
        assertEquals(ActionKeyBuilder.CANONICAL_SCHEMA, binding.get("actionKeySchema"));
        assertEquals(fixture.key.digest().hex(), binding.get("actionKeyDigest"));
        assertEquals("tenant-a", binding.get("actionKeyTenantId"));
        assertEquals("project-a", binding.get("actionKeyProjectId"));
        assertFalse(binding.containsKey("authorizationDecisionId"));
        assertEquals("policy-v1", binding.get("authorizationPolicyVersion"));
        assertEquals("TEST_SOURCE_REF_ALLOWLIST", binding.get("payloadPolicyId"));
        assertEquals("v1", binding.get("payloadPolicyVersion"));
        assertEquals("elmos-action-cache-dispatch/1",
                persisted.requestPayload().get("_elmosCanonicalRequestSchema"));
        assertEquals(outcome.requestDigest().orElseThrow().hex(),
                persisted.requestPayload().get("_elmosCanonicalRequestSha256"));
        Map<?, ?> authorizationAudit = (Map<?, ?>) persisted.requestPayload()
                .get("_elmosAuthorizationAudit");
        assertEquals("decision-1", authorizationAudit.get("decisionId"));
        assertEquals("policy-v1", authorizationAudit.get("policyVersion"));
        assertEquals(outcome.jobId().orElseThrow(), persisted.jobId());
    }

    @Test void forgedOrIncompleteActionKeysFailBeforeAuthorizationAndCacheLookup() {
        Fixture fixture = new Fixture(currentTrust());
        ExecutionJobPort jobs = mock(ExecutionJobPort.class);
        List<ActionCacheExecutionJobDispatcher.Operation> operations = new ArrayList<>();
        ActionCacheExecutionJobDispatcher dispatcher = fixture.dispatcher(
                jobs, (request, operation) -> {
                    operations.add(operation);
                    return allow(request, operation);
                });

        Map<String, String> digestMismatchComponents =
                new LinkedHashMap<>(fixture.key.components());
        digestMismatchComponents.put("source_tree", digest("forged-source").compact());
        ActionKey digestMismatch = new ActionKey(
                fixture.key.digest(), fixture.key.tenantId(), digestMismatchComponents);
        Map<String, String> incompleteComponents =
                new LinkedHashMap<>(fixture.key.components());
        incompleteComponents.remove("policy");
        ActionKey incomplete = new ActionKey(
                fixture.key.digest(), fixture.key.tenantId(), incompleteComponents);
        Map<String, String> tenantAliasComponents =
                new LinkedHashMap<>(fixture.key.components());
        tenantAliasComponents.put("tenant_id", "tenant-z");
        ActionKey tenantAlias = new ActionKey(
                fixture.key.digest(), fixture.key.tenantId(), tenantAliasComponents);

        for (ActionKey forged : List.of(digestMismatch, incomplete, tenantAlias)) {
            ActionCacheExecutionJobDispatcher.Outcome outcome = dispatcher.dispatch(
                    fixture.request(forged, fixture.reader("tenant-a"),
                            ActionCacheExecutionJobDispatcher.Mode.CACHE_OR_ENQUEUE,
                            Map.of("sourceRef", SOURCE_REF), Optional.empty()));
            assertEquals(ActionCacheExecutionJobDispatcher.OutcomeKind.BLOCKED, outcome.kind());
            assertEquals("ACTION_KEY_INVALID", outcome.reason());
        }
        assertTrue(operations.isEmpty());
        verifyNoInteractions(jobs);
    }

    @Test void aLegacyV1DigestCannotImpersonateTheCanonicalV2ActionKey() {
        Fixture fixture = new Fixture(currentTrust());
        ExecutionJobPort jobs = mock(ExecutionJobPort.class);
        List<ActionCacheExecutionJobDispatcher.Operation> operations = new ArrayList<>();
        ActionCacheExecutionJobDispatcher dispatcher = fixture.dispatcher(
                jobs, (request, operation) -> {
                    operations.add(operation);
                    return allow(request, operation);
                });
        ActionKey legacy = new ActionKey(
                legacyV1ActionKeyDigest(fixture.key.components()),
                fixture.key.tenantId(), fixture.key.components());

        ActionCacheExecutionJobDispatcher.Outcome outcome = dispatcher.dispatch(
                fixture.request(legacy, fixture.reader("tenant-a"),
                        ActionCacheExecutionJobDispatcher.Mode.CACHE_OR_ENQUEUE,
                        Map.of("sourceRef", SOURCE_REF), Optional.empty()));

        assertEquals(ActionCacheExecutionJobDispatcher.OutcomeKind.BLOCKED, outcome.kind());
        assertEquals("ACTION_KEY_INVALID", outcome.reason());
        assertTrue(operations.isEmpty());
        verifyNoInteractions(jobs);
    }

    @Test void anIdempotentReplayIsAcceptedWithoutClaimingANewJob() {
        Fixture fixture = new Fixture(currentTrust());
        ExecutionJobPort jobs = mock(ExecutionJobPort.class);
        when(jobs.enqueue(any())).thenReturn("job-existing");
        ActionCacheExecutionJobDispatcher dispatcher = fixture.dispatcher(
                jobs, (request, operation) -> allow(request, operation));

        ActionCacheExecutionJobDispatcher.Outcome outcome =
                dispatcher.dispatch(fixture.request(fixture.reader("tenant-a"),
                        ActionCacheExecutionJobDispatcher.Mode.CACHE_OR_ENQUEUE));

        assertEquals(ActionCacheExecutionJobDispatcher.OutcomeKind.DURABLE_JOB_ACCEPTED,
                outcome.kind());
        assertEquals("job-existing", outcome.jobId().orElseThrow());
        assertTrue(outcome.idempotentReplay());
        assertEquals("DURABLE_JOB_IDEMPOTENT_REPLAY", outcome.reason());
    }

    @Test void canonicalQueueDigestIgnoresMapperSettingsAndNormalizesMapsUnicodeAndDecimals() {
        Fixture first = new Fixture(currentTrust());
        Fixture second = new Fixture(currentTrust());
        ExecutionJobPort firstJobs = mock(ExecutionJobPort.class);
        ExecutionJobPort secondJobs = mock(ExecutionJobPort.class);
        when(firstJobs.enqueue(any())).thenAnswer(invocation ->
                invocation.<ExecutionJobPort.EnqueueCommand>getArgument(0).jobId());
        when(secondJobs.enqueue(any())).thenAnswer(invocation ->
                invocation.<ExecutionJobPort.EnqueueCommand>getArgument(0).jobId());

        Map<String, Object> firstPayload = new LinkedHashMap<>();
        firstPayload.put("sourceRef", SOURCE_REF);
        firstPayload.put("metadata", Map.of(
                "zeta", new BigDecimal("2.00"),
                "alpha", Map.of("second", true, "first", "e\u0301")));
        Map<String, Object> secondPayload = new LinkedHashMap<>();
        secondPayload.put("metadata", Map.of(
                "alpha", Map.of("first", "\u00e9", "second", true),
                "zeta", new BigDecimal("2.0")));
        secondPayload.put("sourceRef", SOURCE_REF);

        ObjectMapper prettyMapper = new ObjectMapper()
                .enable(SerializationFeature.INDENT_OUTPUT);
        ObjectMapper compactMapper = new ObjectMapper()
                .disable(SerializationFeature.INDENT_OUTPUT)
                .disable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS);

        ActionCacheExecutionJobDispatcher.Outcome firstOutcome = first.dispatcher(
                firstJobs, (request, operation) -> allow(request, operation),
                canonicalMetadataPayloadPolicy(), prettyMapper).dispatch(
                first.request(first.reader("tenant-a"),
                        ActionCacheExecutionJobDispatcher.Mode.CACHE_OR_ENQUEUE,
                        firstPayload));
        ActionCacheExecutionJobDispatcher.Outcome secondOutcome = second.dispatcher(
                secondJobs, (request, operation) -> allow(request, operation),
                canonicalMetadataPayloadPolicy(), compactMapper).dispatch(
                second.request(second.reader("tenant-a"),
                        ActionCacheExecutionJobDispatcher.Mode.CACHE_OR_ENQUEUE,
                        secondPayload));

        assertEquals(firstOutcome.requestDigest(), secondOutcome.requestDigest());
    }

    @Test void unknownCurrentTrustOnAnExistingEntryCannotBecomeAQueueMiss() {
        Fixture fixture = new Fixture(ActionCache.TrustRevalidator.failClosedNotConfigured());
        fixture.store();
        ExecutionJobPort jobs = mock(ExecutionJobPort.class);
        ActionCacheExecutionJobDispatcher dispatcher = fixture.dispatcher(
                jobs, (request, operation) -> allow(request, operation));

        ActionCacheExecutionJobDispatcher.Outcome outcome =
                dispatcher.dispatch(fixture.request(fixture.reader("tenant-a"),
                        ActionCacheExecutionJobDispatcher.Mode.CACHE_OR_ENQUEUE));

        assertEquals(ActionCacheExecutionJobDispatcher.OutcomeKind.BLOCKED, outcome.kind());
        assertTrue(outcome.reason().startsWith(
                "CACHE_LOOKUP_DENIED:CURRENT_TRUST_UNKNOWN:"));
        verifyNoInteractions(jobs);
    }

    @Test void crossTenantRequestsAreRejectedBeforeLookupWithoutAnExistenceOracle() {
        Fixture missing = new Fixture(currentTrust());
        Fixture existing = new Fixture(currentTrust());
        existing.store();
        ExecutionJobPort jobs = mock(ExecutionJobPort.class);
        List<ActionCacheExecutionJobDispatcher.Operation> operations = new ArrayList<>();
        ActionCacheExecutionJobDispatcher.Authorizer authorizer = (request, operation) -> {
            operations.add(operation);
            return allow(request, operation);
        };

        ActionCacheExecutionJobDispatcher.Outcome missingOutcome = missing.dispatcher(
                jobs, authorizer).dispatch(missing.request(missing.reader("tenant-b"),
                        ActionCacheExecutionJobDispatcher.Mode.CACHE_OR_ENQUEUE));
        ActionCacheExecutionJobDispatcher.Outcome existingOutcome = existing.dispatcher(
                jobs, authorizer).dispatch(existing.request(existing.reader("tenant-b"),
                        ActionCacheExecutionJobDispatcher.Mode.CACHE_OR_ENQUEUE));

        assertEquals(ActionCacheExecutionJobDispatcher.OutcomeKind.BLOCKED,
                missingOutcome.kind());
        assertEquals(missingOutcome.kind(), existingOutcome.kind());
        assertEquals("REQUEST_TENANT_MISMATCH", missingOutcome.reason());
        assertEquals(missingOutcome.reason(), existingOutcome.reason());
        assertTrue(operations.isEmpty());
        verifyNoInteractions(jobs);
    }

    @Test void unknownExecutionAuthorizationFailsClosedBeforeEnqueue() {
        Fixture fixture = new Fixture(currentTrust());
        ExecutionJobPort jobs = mock(ExecutionJobPort.class);
        ActionCacheExecutionJobDispatcher dispatcher = fixture.dispatcher(jobs,
                (request, operation) -> operation
                        == ActionCacheExecutionJobDispatcher.Operation.CACHE_READ
                        ? allow(request, operation)
                        : ActionCacheExecutionJobDispatcher.AuthorizationDecision.unknown(
                                "PDP_TIMEOUT"));

        ActionCacheExecutionJobDispatcher.Outcome outcome =
                dispatcher.dispatch(fixture.request(fixture.reader("tenant-a"),
                        ActionCacheExecutionJobDispatcher.Mode.CACHE_OR_ENQUEUE));

        assertEquals(ActionCacheExecutionJobDispatcher.OutcomeKind.BLOCKED, outcome.kind());
        assertEquals("EXECUTE_AUTHORIZATION_UNKNOWN:PDP_TIMEOUT", outcome.reason());
        verifyNoInteractions(jobs);
    }

    @Test void everyAllowGrantMustMatchTenantActorAndImmutableActionProject() {
        for (String mismatch : List.of("tenant", "actor", "project")) {
            Fixture fixture = new Fixture(currentTrust());
            ExecutionJobPort jobs = mock(ExecutionJobPort.class);
            ActionCacheExecutionJobDispatcher dispatcher = fixture.dispatcher(jobs,
                    (request, operation) -> {
                        ActionCacheExecutionJobDispatcher.AuthorizationGrant valid =
                                grant(request);
                        ActionCacheExecutionJobDispatcher.AuthorizationGrant invalid =
                                new ActionCacheExecutionJobDispatcher.AuthorizationGrant(
                                        mismatch.equals("tenant") ? "tenant-z" : valid.tenantId(),
                                        mismatch.equals("actor") ? "actor-z" : valid.actorId(),
                                        mismatch.equals("project") ? "project-z" : valid.projectId(),
                                        valid.decisionId(), valid.policyVersion());
                        return ActionCacheExecutionJobDispatcher.AuthorizationDecision.allow(
                                operation.name() + "_ALLOWED", invalid);
                    });

            ActionCacheExecutionJobDispatcher.Outcome outcome = dispatcher.dispatch(
                    fixture.request(fixture.reader("tenant-a"),
                            ActionCacheExecutionJobDispatcher.Mode.CACHE_OR_ENQUEUE));

            assertEquals(ActionCacheExecutionJobDispatcher.OutcomeKind.BLOCKED, outcome.kind());
            assertEquals("CACHE_READ_AUTHORIZATION_GRANT_MISMATCH", outcome.reason());
            verifyNoInteractions(jobs);
        }
    }

    @Test void anAllowDecisionCannotExistWithoutATrustedGrant() {
        assertThrows(IllegalArgumentException.class, () ->
                new ActionCacheExecutionJobDispatcher.AuthorizationDecision(
                        ActionCacheExecutionJobDispatcher.AuthorizationStatus.ALLOW,
                        "TEST_ALLOW", Optional.empty()));
    }

    @Test void aFreshExecuteGrantIsRevalidatedBeforePayloadOrQueueSideEffects() {
        Fixture fixture = new Fixture(currentTrust());
        ExecutionJobPort jobs = mock(ExecutionJobPort.class);
        ActionCacheExecutionJobDispatcher dispatcher = fixture.dispatcher(jobs,
                (request, operation) -> {
                    ActionCacheExecutionJobDispatcher.AuthorizationGrant valid = grant(request);
                    if (operation == ActionCacheExecutionJobDispatcher.Operation.CACHE_READ) {
                        return ActionCacheExecutionJobDispatcher.AuthorizationDecision.allow(
                                "CACHE_READ_ALLOWED", valid);
                    }
                    return ActionCacheExecutionJobDispatcher.AuthorizationDecision.allow(
                            "EXECUTE_ALLOWED",
                            new ActionCacheExecutionJobDispatcher.AuthorizationGrant(
                                    valid.tenantId(), "different-actor", valid.projectId(),
                                    "decision-2", "policy-v2"));
                });

        ActionCacheExecutionJobDispatcher.Outcome outcome = dispatcher.dispatch(
                fixture.request(fixture.reader("tenant-a"),
                        ActionCacheExecutionJobDispatcher.Mode.CACHE_OR_ENQUEUE));

        assertEquals(ActionCacheExecutionJobDispatcher.OutcomeKind.BLOCKED, outcome.kind());
        assertEquals("EXECUTE_AUTHORIZATION_GRANT_MISMATCH", outcome.reason());
        verifyNoInteractions(jobs);
    }

    @Test void anUncertainQueueOutcomeCarriesTheDigestForIdempotentReconciliation() {
        Fixture fixture = new Fixture(currentTrust());
        ExecutionJobPort jobs = mock(ExecutionJobPort.class);
        when(jobs.enqueue(any())).thenThrow(new IllegalStateException("connection reset"));
        ActionCacheExecutionJobDispatcher dispatcher = fixture.dispatcher(
                jobs, (request, operation) -> allow(request, operation));

        ActionCacheExecutionJobDispatcher.Outcome outcome =
                dispatcher.dispatch(fixture.request(fixture.reader("tenant-a"),
                        ActionCacheExecutionJobDispatcher.Mode.CACHE_OR_ENQUEUE));

        assertEquals(
                ActionCacheExecutionJobDispatcher.OutcomeKind.UNKNOWN_RECONCILIATION_REQUIRED,
                outcome.kind());
        assertEquals("QUEUE_OUTCOME_UNKNOWN_RETRY_WITH_EXPECTED_PRIOR_REQUEST_DIGEST",
                outcome.reason());
        assertTrue(outcome.requestDigest().isPresent());
        assertTrue(outcome.jobId().isEmpty());
    }

    @Test void reconciliationRetryReusesTheFirstDigestAfterAuthoritativeAbsentLookup() {
        Fixture fixture = new Fixture(currentTrust());
        ExecutionJobPort jobs = mock(ExecutionJobPort.class);
        when(jobs.enqueue(any())).thenThrow(new IllegalStateException("connection reset"));
        int[] executeDecisions = new int[]{0};
        ActionCacheExecutionJobDispatcher.Authorizer authorizer = (request, operation) -> {
            String decisionId = operation == ActionCacheExecutionJobDispatcher.Operation.EXECUTE
                    ? "decision-execute-" + (++executeDecisions[0])
                    : "decision-read";
            ActionCacheExecutionJobDispatcher.AuthorizationGrant valid = grant(request);
            return ActionCacheExecutionJobDispatcher.AuthorizationDecision.allow(
                    operation.name() + "_ALLOWED",
                    new ActionCacheExecutionJobDispatcher.AuthorizationGrant(
                            valid.tenantId(), valid.actorId(), valid.projectId(), decisionId,
                            valid.policyVersion()));
        };
        ActionCacheExecutionJobDispatcher dispatcher = fixture.dispatcher(jobs, authorizer);

        ActionCacheExecutionJobDispatcher.Request firstRequest = fixture.request(
                fixture.reader("tenant-a"),
                ActionCacheExecutionJobDispatcher.Mode.CACHE_OR_ENQUEUE);
        ActionCacheExecutionJobDispatcher.Outcome first = dispatcher.dispatch(firstRequest);
        CasDigest expected = first.requestDigest().orElseThrow();
        ActionCacheExecutionJobDispatcher.Request retry = fixture.request(
                fixture.key, fixture.reader("tenant-a"),
                ActionCacheExecutionJobDispatcher.Mode.CACHE_OR_ENQUEUE,
                Map.of("sourceRef", SOURCE_REF), Optional.of(expected));
        ActionCacheExecutionJobDispatcher.Outcome second = dispatcher.dispatch(retry);

        assertEquals(
                ActionCacheExecutionJobDispatcher.OutcomeKind.UNKNOWN_RECONCILIATION_REQUIRED,
                first.kind());
        assertEquals(
                ActionCacheExecutionJobDispatcher.OutcomeKind.UNKNOWN_RECONCILIATION_REQUIRED,
                second.kind());
        assertEquals(expected, second.requestDigest().orElseThrow());
        assertEquals("QUEUE_OUTCOME_UNKNOWN_RETRY_WITH_EXPECTED_PRIOR_REQUEST_DIGEST",
                second.reason());
        assertEquals(2, executeDecisions[0],
                "reconciliation must still obtain a fresh EXECUTE authorization");
        ArgumentCaptor<ExecutionJobPort.EnqueueCommand> command =
                ArgumentCaptor.forClass(ExecutionJobPort.EnqueueCommand.class);
        verify(jobs, times(2)).enqueue(command.capture());
        Map<?, ?> firstAudit = (Map<?, ?>) command.getAllValues().get(0).requestPayload()
                .get("_elmosAuthorizationAudit");
        assertEquals("decision-execute-1", firstAudit.get("decisionId"));
    }

    @Test void reconciliationReturnsThePersistedJobAfterDigestBoundLookup() {
        Fixture fixture = new Fixture(currentTrust());
        ExecutionJobPort jobs = mock(ExecutionJobPort.class);
        when(jobs.enqueue(any())).thenThrow(new IllegalStateException("connection reset"));
        ActionCacheExecutionJobDispatcher dispatcher = fixture.dispatcher(
                jobs, ActionCacheExecutionJobDispatcherTest::allow);

        ActionCacheExecutionJobDispatcher.Outcome first = dispatcher.dispatch(
                fixture.request(fixture.reader("tenant-a"),
                        ActionCacheExecutionJobDispatcher.Mode.CACHE_OR_ENQUEUE));
        CasDigest expected = first.requestDigest().orElseThrow();
        when(jobs.findByIdempotencyKey("tenant-a", "action-cache:test-1"))
                .thenReturn(Optional.of(new ExecutionJobPort.IdempotencyLookup(
                        "job-reconciled", expected.hex(), ExecutionJobPort.Status.QUEUED)));

        ActionCacheExecutionJobDispatcher.Outcome reconciled = dispatcher.dispatch(
                fixture.request(fixture.key, fixture.reader("tenant-a"),
                        ActionCacheExecutionJobDispatcher.Mode.CACHE_OR_ENQUEUE,
                        Map.of("sourceRef", SOURCE_REF), Optional.of(expected)));

        assertEquals(ActionCacheExecutionJobDispatcher.OutcomeKind.DURABLE_JOB_ACCEPTED,
                reconciled.kind());
        assertEquals("DURABLE_JOB_RECONCILED", reconciled.reason());
        assertEquals(Optional.of("job-reconciled"), reconciled.jobId());
        assertEquals(Optional.of(expected), reconciled.requestDigest());
        assertTrue(reconciled.idempotentReplay());
        verify(jobs, times(1)).enqueue(any());
    }

    @Test void reconciliationRefusesAJobWhosePersistedDigestDiffers() {
        Fixture fixture = new Fixture(currentTrust());
        ExecutionJobPort jobs = mock(ExecutionJobPort.class);
        when(jobs.enqueue(any())).thenThrow(new IllegalStateException("connection reset"));
        ActionCacheExecutionJobDispatcher dispatcher = fixture.dispatcher(
                jobs, ActionCacheExecutionJobDispatcherTest::allow);

        ActionCacheExecutionJobDispatcher.Outcome first = dispatcher.dispatch(
                fixture.request(fixture.reader("tenant-a"),
                        ActionCacheExecutionJobDispatcher.Mode.CACHE_OR_ENQUEUE));
        CasDigest expected = first.requestDigest().orElseThrow();
        when(jobs.findByIdempotencyKey("tenant-a", "action-cache:test-1"))
                .thenReturn(Optional.of(new ExecutionJobPort.IdempotencyLookup(
                        "job-reconciled", digest("different-request").hex(),
                        ExecutionJobPort.Status.QUEUED)));

        ActionCacheExecutionJobDispatcher.Outcome reconciled = dispatcher.dispatch(
                fixture.request(fixture.key, fixture.reader("tenant-a"),
                        ActionCacheExecutionJobDispatcher.Mode.CACHE_OR_ENQUEUE,
                        Map.of("sourceRef", SOURCE_REF), Optional.of(expected)));

        assertReconciliationPending(reconciled, expected);
        assertEquals("RECONCILIATION_PERSISTED_REQUEST_DIGEST_MISMATCH",
                reconciled.reason());
        verify(jobs, times(1)).enqueue(any());
    }

    @Test void reconciliationMaterialDriftRemainsUnknownAndDoesNotRetryTheQueue() {
        Fixture fixture = new Fixture(currentTrust());
        ExecutionJobPort jobs = mock(ExecutionJobPort.class);
        when(jobs.enqueue(any())).thenThrow(new IllegalStateException("connection reset"));
        ActionCacheExecutionJobDispatcher dispatcher = fixture.dispatcher(
                jobs, (request, operation) -> allow(request, operation));
        ActionCacheExecutionJobDispatcher.Outcome first = dispatcher.dispatch(
                fixture.request(fixture.reader("tenant-a"),
                        ActionCacheExecutionJobDispatcher.Mode.CACHE_OR_ENQUEUE));
        CasDigest expectedPrior = first.requestDigest().orElseThrow();
        String changedSourceRef = "cas:sha256:" + "c".repeat(64);
        ActionCacheExecutionJobDispatcher.Request retry = fixture.request(
                fixture.key, fixture.reader("tenant-a"),
                ActionCacheExecutionJobDispatcher.Mode.CACHE_OR_ENQUEUE,
                Map.of("sourceRef", changedSourceRef), Optional.of(expectedPrior));

        ActionCacheExecutionJobDispatcher.Outcome outcome = dispatcher.dispatch(retry);

        assertEquals(
                ActionCacheExecutionJobDispatcher.OutcomeKind.UNKNOWN_RECONCILIATION_REQUIRED,
                first.kind());
        assertEquals(
                ActionCacheExecutionJobDispatcher.OutcomeKind.UNKNOWN_RECONCILIATION_REQUIRED,
                outcome.kind());
        assertEquals("RECONCILIATION_MATERIAL_DRIFT_NO_QUEUE_RETRY", outcome.reason());
        assertEquals(expectedPrior, outcome.requestDigest().orElseThrow());
        assertTrue(outcome.jobId().isEmpty());
        verify(jobs, times(1)).enqueue(any());
    }

    @Test void reconciliationAuthorizationDenyOrUnknownPreservesThePriorSubject() {
        for (ActionCacheExecutionJobDispatcher.Operation rejectedOperation
                : ActionCacheExecutionJobDispatcher.Operation.values()) {
            for (ActionCacheExecutionJobDispatcher.AuthorizationStatus status : List.of(
                    ActionCacheExecutionJobDispatcher.AuthorizationStatus.DENY,
                    ActionCacheExecutionJobDispatcher.AuthorizationStatus.UNKNOWN)) {
                Fixture fixture = new Fixture(currentTrust());
                ExecutionJobPort jobs = mock(ExecutionJobPort.class);
                CasDigest prior = digest(rejectedOperation + "-" + status + "-prior");
                ActionCacheExecutionJobDispatcher dispatcher = fixture.dispatcher(
                        jobs, (request, operation) -> {
                            if (operation != rejectedOperation) {
                                return allow(request, operation);
                            }
                            return status == ActionCacheExecutionJobDispatcher.AuthorizationStatus.DENY
                                    ? ActionCacheExecutionJobDispatcher.AuthorizationDecision.deny(
                                            "TEST_POLICY_DENY")
                                    : ActionCacheExecutionJobDispatcher.AuthorizationDecision.unknown(
                                            "TEST_POLICY_UNKNOWN");
                        });

                ActionCacheExecutionJobDispatcher.Outcome outcome = dispatcher.dispatch(
                        fixture.request(fixture.key, fixture.reader("tenant-a"),
                                ActionCacheExecutionJobDispatcher.Mode.CACHE_OR_ENQUEUE,
                                Map.of("sourceRef", SOURCE_REF), Optional.of(prior)));

                assertReconciliationPending(outcome, prior);
                assertTrue(outcome.reason().startsWith("RECONCILIATION_PENDING:"));
                verifyNoInteractions(jobs);
            }
        }
    }

    @Test void reconciliationCacheHitIsNotMistakenForAQueueConfirmation() {
        Fixture fixture = new Fixture(currentTrust());
        fixture.store();
        ExecutionJobPort jobs = mock(ExecutionJobPort.class);
        CasDigest prior = digest("cache-hit-prior");
        ActionCacheExecutionJobDispatcher dispatcher = fixture.dispatcher(
                jobs, ActionCacheExecutionJobDispatcherTest::allow);

        ActionCacheExecutionJobDispatcher.Outcome outcome = dispatcher.dispatch(
                fixture.request(fixture.key, fixture.reader("tenant-a"),
                        ActionCacheExecutionJobDispatcher.Mode.CACHE_OR_ENQUEUE,
                        Map.of("sourceRef", SOURCE_REF), Optional.of(prior)));

        assertReconciliationPending(outcome, prior);
        assertEquals("CACHE_HIT_IS_NOT_QUEUE_RECONCILIATION", outcome.reason());
        assertEquals(Optional.of(ActionCache.CacheOutcome.HIT), outcome.cacheOutcome());
        verifyNoInteractions(jobs);
    }

    @Test void reconciliationCacheDenialPreservesThePriorSubject() {
        Fixture fixture = new Fixture(ActionCache.TrustRevalidator.failClosedNotConfigured());
        fixture.store();
        ExecutionJobPort jobs = mock(ExecutionJobPort.class);
        CasDigest prior = digest("cache-denied-prior");
        ActionCacheExecutionJobDispatcher dispatcher = fixture.dispatcher(
                jobs, ActionCacheExecutionJobDispatcherTest::allow);

        ActionCacheExecutionJobDispatcher.Outcome outcome = dispatcher.dispatch(
                fixture.request(fixture.key, fixture.reader("tenant-a"),
                        ActionCacheExecutionJobDispatcher.Mode.CACHE_OR_ENQUEUE,
                        Map.of("sourceRef", SOURCE_REF), Optional.of(prior)));

        assertReconciliationPending(outcome, prior);
        assertTrue(outcome.reason().startsWith(
                "RECONCILIATION_PENDING:CACHE_LOOKUP_DENIED:"));
        assertEquals(Optional.of(ActionCache.CacheOutcome.DENIED), outcome.cacheOutcome());
        verifyNoInteractions(jobs);
    }

    @Test void reconciliationCacheFailurePreservesThePriorSubject() {
        ActionCacheIndex unavailableIndex = mock(ActionCacheIndex.class);
        when(unavailableIndex.find(any())).thenThrow(new IllegalStateException("database unavailable"));
        Fixture fixture = new Fixture(currentTrust(), unavailableIndex);
        ExecutionJobPort jobs = mock(ExecutionJobPort.class);
        CasDigest prior = digest("cache-unavailable-prior");
        ActionCacheExecutionJobDispatcher dispatcher = fixture.dispatcher(
                jobs, ActionCacheExecutionJobDispatcherTest::allow);

        ActionCacheExecutionJobDispatcher.Outcome outcome = dispatcher.dispatch(
                fixture.request(fixture.key, fixture.reader("tenant-a"),
                        ActionCacheExecutionJobDispatcher.Mode.CACHE_OR_ENQUEUE,
                        Map.of("sourceRef", SOURCE_REF), Optional.of(prior)));

        assertReconciliationPending(outcome, prior);
        assertEquals("RECONCILIATION_PENDING:CACHE_LOOKUP_UNAVAILABLE", outcome.reason());
        verifyNoInteractions(jobs);
    }

    @Test void reconciliationCacheOnlyAndSanitizerFailuresPreserveThePriorSubject() {
        Fixture fixture = new Fixture(currentTrust());
        CasDigest cacheOnlyPrior = digest("cache-only-prior");
        ExecutionJobPort cacheOnlyJobs = mock(ExecutionJobPort.class);
        ActionCacheExecutionJobDispatcher cacheOnlyDispatcher = fixture.dispatcher(
                cacheOnlyJobs, ActionCacheExecutionJobDispatcherTest::allow);

        ActionCacheExecutionJobDispatcher.Outcome cacheOnly = cacheOnlyDispatcher.dispatch(
                fixture.request(fixture.key, fixture.reader("tenant-a"),
                        ActionCacheExecutionJobDispatcher.Mode.CACHE_ONLY,
                        Map.of("sourceRef", SOURCE_REF), Optional.of(cacheOnlyPrior)));

        assertReconciliationPending(cacheOnly, cacheOnlyPrior);
        assertEquals("CACHE_ONLY_IS_NOT_QUEUE_RECONCILIATION", cacheOnly.reason());
        verifyNoInteractions(cacheOnlyJobs);

        CasDigest sanitizerPrior = digest("sanitizer-prior");
        ExecutionJobPort sanitizerJobs = mock(ExecutionJobPort.class);
        ActionCacheExecutionJobDispatcher sanitizerDispatcher = fixture.dispatcher(
                sanitizerJobs, ActionCacheExecutionJobDispatcherTest::allow);
        ActionCacheExecutionJobDispatcher.Outcome sanitizerFailure = sanitizerDispatcher.dispatch(
                fixture.request(fixture.key, fixture.reader("tenant-a"),
                        ActionCacheExecutionJobDispatcher.Mode.CACHE_OR_ENQUEUE,
                        Map.of("sourceRef", SOURCE_REF, "notAllowlisted", true),
                        Optional.of(sanitizerPrior)));

        assertReconciliationPending(sanitizerFailure, sanitizerPrior);
        assertEquals("RECONCILIATION_PENDING:DISPATCH_REQUEST_INVALID",
                sanitizerFailure.reason());
        verifyNoInteractions(sanitizerJobs);
    }

    @Test void queueIdempotencyConflictRetainsDigestAndRequiresReconciliation() {
        Fixture fixture = new Fixture(currentTrust());
        ExecutionJobPort jobs = mock(ExecutionJobPort.class);
        when(jobs.enqueue(any())).thenThrow(new ExecutionJobPort.ExecutionStateException(
                "ELMOS_EXECUTION_IDEMPOTENCY_CONFLICT"));
        ActionCacheExecutionJobDispatcher dispatcher = fixture.dispatcher(
                jobs, (request, operation) -> allow(request, operation));

        ActionCacheExecutionJobDispatcher.Outcome outcome = dispatcher.dispatch(
                fixture.request(fixture.reader("tenant-a"),
                        ActionCacheExecutionJobDispatcher.Mode.CACHE_OR_ENQUEUE));

        assertEquals(
                ActionCacheExecutionJobDispatcher.OutcomeKind.UNKNOWN_RECONCILIATION_REQUIRED,
                outcome.kind());
        assertEquals("QUEUE_IDEMPOTENCY_CONFLICT_RECONCILIATION_REQUIRED", outcome.reason());
        assertTrue(outcome.requestDigest().isPresent());
    }

    @Test void nonConflictQueueRejectionStillRequiresDigestBoundReconciliation() {
        Fixture fixture = new Fixture(currentTrust());
        ExecutionJobPort jobs = mock(ExecutionJobPort.class);
        when(jobs.enqueue(any())).thenThrow(new ExecutionJobPort.ExecutionStateException(
                "ELMOS_EXECUTION_TRANSIENT_STATE"));
        ActionCacheExecutionJobDispatcher dispatcher = fixture.dispatcher(
                jobs, ActionCacheExecutionJobDispatcherTest::allow);

        ActionCacheExecutionJobDispatcher.Outcome outcome = dispatcher.dispatch(
                fixture.request(fixture.reader("tenant-a"),
                        ActionCacheExecutionJobDispatcher.Mode.CACHE_OR_ENQUEUE));

        assertEquals(
                ActionCacheExecutionJobDispatcher.OutcomeKind.UNKNOWN_RECONCILIATION_REQUIRED,
                outcome.kind());
        assertEquals("QUEUE_REJECTED_RECONCILIATION_REQUIRED", outcome.reason());
        assertTrue(outcome.requestDigest().isPresent());
        assertTrue(outcome.jobId().isEmpty());
    }

    @Test void anInvalidDurableJobIdentityRequiresReconciliationRatherThanSuccess() {
        Fixture fixture = new Fixture(currentTrust());
        ExecutionJobPort jobs = mock(ExecutionJobPort.class);
        when(jobs.enqueue(any())).thenReturn("job id from an untrusted response");
        ActionCacheExecutionJobDispatcher dispatcher = fixture.dispatcher(
                jobs, (request, operation) -> allow(request, operation));

        ActionCacheExecutionJobDispatcher.Outcome outcome =
                dispatcher.dispatch(fixture.request(fixture.reader("tenant-a"),
                        ActionCacheExecutionJobDispatcher.Mode.CACHE_OR_ENQUEUE));

        assertEquals(
                ActionCacheExecutionJobDispatcher.OutcomeKind.UNKNOWN_RECONCILIATION_REQUIRED,
                outcome.kind());
        assertEquals("QUEUE_RETURNED_INVALID_JOB_ID_RECONCILE_WITH_PRIOR_REQUEST_DIGEST",
                outcome.reason());
        assertTrue(outcome.requestDigest().isPresent());
        assertTrue(outcome.jobId().isEmpty());
    }

    @Test void malformedAuthorizationReasonBecomesAnUnknownDecision() {
        Fixture fixture = new Fixture(currentTrust());
        ExecutionJobPort jobs = mock(ExecutionJobPort.class);
        ActionCacheExecutionJobDispatcher dispatcher = fixture.dispatcher(jobs,
                (request, operation) -> operation
                        == ActionCacheExecutionJobDispatcher.Operation.CACHE_READ
                        ? allow(request, operation)
                        : ActionCacheExecutionJobDispatcher.AuthorizationDecision.allow(
                                "free form reason with spaces", grant(request)));

        ActionCacheExecutionJobDispatcher.Outcome outcome =
                dispatcher.dispatch(fixture.request(fixture.reader("tenant-a"),
                        ActionCacheExecutionJobDispatcher.Mode.CACHE_OR_ENQUEUE));

        assertEquals(ActionCacheExecutionJobDispatcher.OutcomeKind.BLOCKED, outcome.kind());
        assertEquals(
                "EXECUTE_AUTHORIZATION_UNKNOWN:AUTHORIZATION_PROVIDER_UNAVAILABLE",
                outcome.reason());
        verifyNoInteractions(jobs);
    }

    @Test void cacheOnlyMissDoesNotAskForExecuteAuthorizationOrEnqueue() {
        Fixture fixture = new Fixture(currentTrust());
        ExecutionJobPort jobs = mock(ExecutionJobPort.class);
        List<ActionCacheExecutionJobDispatcher.Operation> operations = new ArrayList<>();
        ActionCacheExecutionJobDispatcher dispatcher = fixture.dispatcher(
                jobs, (request, operation) -> {
                    operations.add(operation);
                    return allow(request, operation);
                });

        ActionCacheExecutionJobDispatcher.Outcome outcome =
                dispatcher.dispatch(fixture.request(fixture.reader("tenant-a"),
                        ActionCacheExecutionJobDispatcher.Mode.CACHE_ONLY));

        assertEquals(ActionCacheExecutionJobDispatcher.OutcomeKind.NOT_ENQUEUED,
                outcome.kind());
        assertEquals(List.of(ActionCacheExecutionJobDispatcher.Operation.CACHE_READ), operations);
        verify(jobs, never()).enqueue(any());
    }

    @Test void deploymentPayloadPolicyRejectsUnallowlistedRawCallerFields() {
        Fixture fixture = new Fixture(currentTrust());
        ExecutionJobPort jobs = mock(ExecutionJobPort.class);
        ActionCacheExecutionJobDispatcher dispatcher = fixture.dispatcher(
                jobs, (request, operation) -> allow(request, operation));

        ActionCacheExecutionJobDispatcher.Outcome outcome = dispatcher.dispatch(
                fixture.request(fixture.reader("tenant-a"),
                        ActionCacheExecutionJobDispatcher.Mode.CACHE_OR_ENQUEUE,
                        Map.of("sourceRef", SOURCE_REF, "callerNote", "must-not-persist")));

        assertEquals(ActionCacheExecutionJobDispatcher.OutcomeKind.BLOCKED, outcome.kind());
        assertEquals("DISPATCH_REQUEST_INVALID", outcome.reason());
        verifyNoInteractions(jobs);
    }

    @Test void onlyTypedOpaqueSecretReferencesCanReachTheCanonicalPayload() {
        Fixture fixture = new Fixture(currentTrust());
        ExecutionJobPort jobs = mock(ExecutionJobPort.class);
        when(jobs.enqueue(any())).thenAnswer(invocation ->
                invocation.<ExecutionJobPort.EnqueueCommand>getArgument(0).jobId());
        ActionCacheExecutionJobDispatcher.PayloadPolicy secretReferencePolicy = context -> {
            Map<String, Object> raw = context.request().dispatch().payload();
            if (!raw.keySet().equals(Set.of("sourceRef", "credentialRef"))
                    || !(raw.get("sourceRef") instanceof String sourceRef)
                    || !sourceRef.matches("^cas:sha256:[0-9a-f]{64}$")
                    || !(raw.get("credentialRef")
                            instanceof ActionCacheExecutionJobDispatcher.SecretReference
                            reference)) {
                throw new IllegalArgumentException("typed credential reference required");
            }
            return new ActionCacheExecutionJobDispatcher.SanitizedPayload(
                    "TEST_SECRET_REF_ALLOWLIST", "v1",
                    Map.of("sourceRef", sourceRef, "credentialRef", reference));
        };
        ActionCacheExecutionJobDispatcher dispatcher = fixture.dispatcher(
                jobs, (request, operation) -> allow(request, operation),
                secretReferencePolicy, new ObjectMapper());

        ActionCacheExecutionJobDispatcher.Outcome outcome = dispatcher.dispatch(
                fixture.request(fixture.reader("tenant-a"),
                        ActionCacheExecutionJobDispatcher.Mode.CACHE_OR_ENQUEUE,
                        Map.of("sourceRef", SOURCE_REF, "credentialRef",
                                new ActionCacheExecutionJobDispatcher.SecretReference(
                                        "secretref://vault/tenant-a/compiler#version-7"))));

        assertEquals(ActionCacheExecutionJobDispatcher.OutcomeKind.DURABLE_JOB_ACCEPTED,
                outcome.kind());
        ArgumentCaptor<ExecutionJobPort.EnqueueCommand> command =
                ArgumentCaptor.forClass(ExecutionJobPort.EnqueueCommand.class);
        verify(jobs).enqueue(command.capture());
        Map<?, ?> reference = (Map<?, ?>) command.getValue().requestPayload()
                .get("credentialRef");
        assertEquals("ELMOS_SECRET_REFERENCE", reference.get("kind"));
        assertEquals("secretref://vault/tenant-a/compiler#version-7",
                reference.get("opaqueReference"));
        assertFalse(command.getValue().requestPayload().toString().contains("password"));
    }

    @Test void mutableImagesAndSensitivePayloadsAreRejectedBeforeAnySideEffect() {
        assertThrows(IllegalArgumentException.class, () -> Fixture.spec(
                Map.of("sourceRef", SOURCE_REF), "registry/elmos:latest"));
        assertThrows(IllegalArgumentException.class, () -> Fixture.spec(
                Map.of("accessToken", "forbidden"), IMAGE));
        assertThrows(IllegalArgumentException.class, () -> Fixture.spec(
                Map.of("sourceRef", SOURCE_REF, "weight", 0.1d), IMAGE));
        assertThrows(IllegalArgumentException.class, () -> Fixture.spec(
                Map.of("sourceRef", SOURCE_REF, "unordered", Set.of("a", "b")), IMAGE));
        assertThrows(IllegalArgumentException.class, () -> Fixture.spec(
                Map.of("sourceRef", SOURCE_REF,
                        "oversized", "x".repeat(64 * 1024 + 1)), IMAGE));
        assertThrows(IllegalArgumentException.class, () -> Fixture.spec(
                Map.of("sourceRef", SOURCE_REF,
                        "oversizedInteger", BigInteger.ONE.shiftLeft(8_193)), IMAGE));
        assertThrows(IllegalArgumentException.class, () -> Fixture.spec(
                Map.of("sourceRef", SOURCE_REF,
                        "oversizedDecimal", new BigDecimal(BigInteger.ONE, 20_000)), IMAGE));
        assertThrows(IllegalArgumentException.class, () -> Fixture.spec(
                Map.of("sourceRef", SOURCE_REF,
                        "aggregate", Collections.nCopies(
                                17, "x".repeat(64 * 1024))), IMAGE));
    }

    @Test void actionCacheDispatchCannotEnableAutomaticQueueRetries() {
        for (short maxAttempts = 2; maxAttempts <= 5; maxAttempts++) {
            short rejected = maxAttempts;
            assertThrows(IllegalArgumentException.class, () -> Fixture.spec(
                    Map.of("sourceRef", SOURCE_REF), IMAGE, rejected));
        }
    }

    @Test void pathologicallyDeepPayloadIsRejectedBeforeAnySideEffect() {
        Map<String, Object> payload = new LinkedHashMap<>();
        Map<String, Object> cursor = payload;
        for (int depth = 0; depth < 34; depth++) {
            Map<String, Object> nested = new LinkedHashMap<>();
            cursor.put("nested", nested);
            cursor = nested;
        }

        assertThrows(IllegalArgumentException.class, () -> Fixture.spec(payload, IMAGE));
    }

    @Test void canonicalEncoderFailsFastAtOneMiBBeforeQueueSideEffects() {
        Fixture fixture = new Fixture(currentTrust());
        ExecutionJobPort jobs = mock(ExecutionJobPort.class);
        String chunk = "x".repeat(64 * 1024);
        Map<String, Object> raw = Map.of("sourceRef", SOURCE_REF);
        ActionCacheExecutionJobDispatcher.PayloadPolicy boundedPolicy = context ->
                new ActionCacheExecutionJobDispatcher.SanitizedPayload(
                    "TEST_BOUNDED_ALLOWLIST", "v1",
                        Map.of("sourceRef", SOURCE_REF,
                                "chunks", Collections.nCopies(17, chunk)));
        ActionCacheExecutionJobDispatcher dispatcher = fixture.dispatcher(
                jobs, (request, operation) -> allow(request, operation),
                boundedPolicy, new ObjectMapper());

        ActionCacheExecutionJobDispatcher.Outcome outcome = dispatcher.dispatch(
                fixture.request(fixture.reader("tenant-a"),
                        ActionCacheExecutionJobDispatcher.Mode.CACHE_OR_ENQUEUE, raw));

        assertEquals(ActionCacheExecutionJobDispatcher.OutcomeKind.BLOCKED, outcome.kind());
        assertEquals("DISPATCH_REQUEST_INVALID", outcome.reason());
        verifyNoInteractions(jobs);
    }

    private static ActionCacheExecutionJobDispatcher.AuthorizationDecision allow(
            ActionCacheExecutionJobDispatcher.Request request,
            ActionCacheExecutionJobDispatcher.Operation operation
    ) {
        return ActionCacheExecutionJobDispatcher.AuthorizationDecision.allow(
                operation.name() + "_ALLOWED", grant(request));
    }

    private static void assertReconciliationPending(
            ActionCacheExecutionJobDispatcher.Outcome outcome,
            CasDigest expectedPriorRequestDigest
    ) {
        assertEquals(
                ActionCacheExecutionJobDispatcher.OutcomeKind.UNKNOWN_RECONCILIATION_REQUIRED,
                outcome.kind());
        assertEquals(expectedPriorRequestDigest, outcome.requestDigest().orElseThrow());
        assertTrue(outcome.jobId().isEmpty());
        assertFalse(outcome.idempotentReplay());
    }

    private static ActionCacheExecutionJobDispatcher.AuthorizationGrant grant(
            ActionCacheExecutionJobDispatcher.Request request
    ) {
        return new ActionCacheExecutionJobDispatcher.AuthorizationGrant(
                request.reader().tenantId(), request.dispatch().actorId(),
                request.key().components().get("project_id"),
                "decision-1", "policy-v1");
    }

    private static ActionCacheExecutionJobDispatcher.PayloadPolicy strictSourcePayloadPolicy() {
        return context -> {
            Map<String, Object> raw = context.request().dispatch().payload();
            if (!raw.keySet().equals(Set.of("sourceRef"))
                    || !(raw.get("sourceRef") instanceof String sourceRef)
                    || !sourceRef.matches("^cas:sha256:[0-9a-f]{64}$")) {
                throw new IllegalArgumentException("only one canonical sourceRef is permitted");
            }
            return new ActionCacheExecutionJobDispatcher.SanitizedPayload(
                    "TEST_SOURCE_REF_ALLOWLIST", "v1", Map.of("sourceRef", sourceRef));
        };
    }

    private static ActionCacheExecutionJobDispatcher.PayloadPolicy
    canonicalMetadataPayloadPolicy() {
        return context -> {
            Map<String, Object> raw = context.request().dispatch().payload();
            if (!raw.keySet().equals(Set.of("sourceRef", "metadata"))
                    || !(raw.get("sourceRef") instanceof String sourceRef)
                    || !sourceRef.matches("^cas:sha256:[0-9a-f]{64}$")
                    || !(raw.get("metadata") instanceof Map<?, ?> metadata)) {
                throw new IllegalArgumentException("canonical metadata payload is invalid");
            }
            return new ActionCacheExecutionJobDispatcher.SanitizedPayload(
                    "TEST_METADATA_ALLOWLIST", "v1",
                    Map.of("sourceRef", sourceRef, "metadata", metadata));
        };
    }

    private static ActionCache.TrustRevalidator currentTrust() {
        return new ActionCache.TrustRevalidator() {
            @Override
            public ActionCache.TrustDecision revalidate(
                    ActionCache.Entry entry, long nowEpochMillis
            ) {
                return ActionCache.TrustDecision.trusted("TEST_CURRENT_TRUST");
            }

            @Override
            public String mode() {
                return "TEST_CURRENT_TRUST";
            }
        };
    }

    private static final class Fixture {
        private final InMemoryCasStore store = new InMemoryCasStore("objects");
        private final ActionCache cache;
        private final ActionKey key = key();

        private Fixture(ActionCache.TrustRevalidator trustRevalidator) {
            this(trustRevalidator, new InMemoryActionCacheIndex());
        }

        private Fixture(
                ActionCache.TrustRevalidator trustRevalidator,
                ActionCacheIndex index
        ) {
            cache = new ActionCache(TenantCasStore.global(store), new CasAccessPolicy(),
                    ActionCache.FailureCachePolicy.none(),
                    ActionCache.SampleRecomputePolicy.disabled(), () -> 1_000_000L,
                    new CasMetrics(), index, CasTelemetry.noop(),
                    trustRevalidator);
        }

        private ActionCacheExecutionJobDispatcher dispatcher(
                ExecutionJobPort jobs,
                ActionCacheExecutionJobDispatcher.Authorizer authorizer
        ) {
            return new ActionCacheExecutionJobDispatcher(
                    cache, jobs, authorizer, strictSourcePayloadPolicy());
        }

        private ActionCacheExecutionJobDispatcher dispatcher(
                ExecutionJobPort jobs,
                ActionCacheExecutionJobDispatcher.Authorizer authorizer,
                ActionCacheExecutionJobDispatcher.PayloadPolicy payloadPolicy,
                ObjectMapper applicationJson
        ) {
            return new ActionCacheExecutionJobDispatcher(
                    cache, jobs, authorizer, payloadPolicy, applicationJson);
        }

        private void store() {
            cache.put(key, success(), producer(),
                    new ActionCache.WriterIdentity(
                            "runner", "elmos.internal", "node-1", true),
                    ActionCache.RiskTier.STANDARD, Optional.empty());
        }

        private ActionResultRecord success() {
            byte[] bytes = "cached output".getBytes(StandardCharsets.UTF_8);
            CasDigest output = CasDigest.of(bytes);
            store.put(output, bytes);
            return ActionResultRecord.succeeded("action-1", "receipt-1", output,
                    digest("provenance"), new ActionResultRecord.ResourceUsage(
                            1, 128, 10, 20, 0, 2), "start", "finish");
        }

        private CasAccessPolicy.ProducerContext producer() {
            return new CasAccessPolicy.ProducerContext(
                    "tenant-a", "project-a", Set.of("repo:read"), "eu-west",
                    CasAccessPolicy.SecurityTier.INTERNAL,
                    CasObjectModel.Sensitivity.GENERATED_OUTPUT, IMAGE,
                    Optional.of(digest("producer provenance")));
        }

        private CasAccessPolicy.ReaderContext reader(String tenant) {
            return new CasAccessPolicy.ReaderContext(
                    tenant, Set.of("repo:read"), "eu-west",
                    CasAccessPolicy.SecurityTier.INTERNAL, false);
        }

        private ActionCacheExecutionJobDispatcher.Request request(
                CasAccessPolicy.ReaderContext reader,
                ActionCacheExecutionJobDispatcher.Mode mode
        ) {
            return request(reader, mode, Map.of("sourceRef", SOURCE_REF));
        }

        private ActionCacheExecutionJobDispatcher.Request request(
                CasAccessPolicy.ReaderContext reader,
                ActionCacheExecutionJobDispatcher.Mode mode,
                Map<String, Object> payload
        ) {
            return request(key, reader, mode, payload, Optional.empty());
        }

        private ActionCacheExecutionJobDispatcher.Request request(
                ActionKey actionKey,
                CasAccessPolicy.ReaderContext reader,
                ActionCacheExecutionJobDispatcher.Mode mode,
                Map<String, Object> payload,
                Optional<CasDigest> expectedPriorRequestDigest
        ) {
            return new ActionCacheExecutionJobDispatcher.Request(
                    actionKey, reader, spec(payload, IMAGE),
                    false, mode, expectedPriorRequestDigest);
        }

        private static ActionCacheExecutionJobDispatcher.DispatchSpec spec(
                Map<String, Object> payload, String image
        ) {
            return spec(payload, image, (short) 1);
        }

        private static ActionCacheExecutionJobDispatcher.DispatchSpec spec(
                Map<String, Object> payload, String image, short maxAttempts
        ) {
            return new ActionCacheExecutionJobDispatcher.DispatchSpec(
                    "actor-a", ExecutionJobPort.BusinessLine.GENERATION,
                    "compile", "action-cache:test-1", payload,
                    "generation:multi", image, (short) 100, 3600, maxAttempts);
        }

        private static ActionKey key() {
            return new ActionKeyBuilder()
                    .tenant("tenant-a", "project-a")
                    .sourceTree(digest("source"))
                    .dependencyGraph(digest("dependencies"))
                    .adapter("java", digest("adapter"))
                    .irSchemaVersion("ir-v3")
                    .rulePacks(List.of(
                            new ActionKeyBuilder.RulePackRef("java-rules", digest("rules"))))
                    .toolchainImage(IMAGE)
                    .targetPlatform("linux/arm64")
                    .buildOptions(Map.of("profile", "release"))
                    .command(List.of("./mvnw", "verify"))
                    .workingDirectory("/workspace/source")
                    .declaredOutputs(List.of("target"))
                    .prompt(Optional.of(digest("prompt")))
                    .model(Optional.of(new ActionKeyBuilder.ModelIdentity(
                            "local", "compiler-model", "v1", Map.of("temperature", "0"))))
                    .policy(digest("policy"))
                    .permissionScope(Set.of("repo:read"))
                    .sandbox("S2", digest("sandbox"))
                    .dataResidency("eu-west")
                    .environmentContract(ActionKeyBuilder.EnvironmentContract.of())
                    .environment(Map.of())
                    .build();
        }
    }

    private static CasDigest digest(String value) {
        return CasDigest.ofUtf8(value);
    }

    private static CasDigest legacyV1ActionKeyDigest(Map<String, String> components) {
        StringBuilder encoded = new StringBuilder();
        appendLegacyV1Field(encoded, "elmos-action-key/1");
        components.forEach((name, value) -> {
            appendLegacyV1Field(encoded, name);
            appendLegacyV1Field(encoded, value);
        });
        return CasDigest.of(encoded.toString().getBytes(StandardCharsets.UTF_8));
    }

    private static void appendLegacyV1Field(StringBuilder encoded, String value) {
        encoded.append(value.getBytes(StandardCharsets.UTF_8).length)
                .append(':').append(value).append('\n');
    }
}
