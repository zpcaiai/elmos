package io.elmos.workflow;

import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class TenantLifecyclePolicyTest {
    private static final Instant AUTHENTICATED_AT =
            Instant.parse("2026-08-25T00:00:00Z");
    private static final Instant NOW = Instant.parse("2026-08-25T01:00:00Z");
    private static final String DIGEST_A = "a".repeat(64);
    private static final String DIGEST_B = "b".repeat(64);
    private static final String DIGEST_C = "c".repeat(64);

    @Test
    void bindingFailsClosedForAnonymousExpiredCrossAccountAndMissingPermission() {
        var resource = resource("org-a", "account-a", "tenant-a");
        var request = request(TenantLifecyclePolicy.Operation.DELETE);

        assertCode("ELMOS_MTF_AUTHENTICATION_REQUIRED", () ->
                TenantLifecyclePolicy.bind(principal(
                        "org-a", "account-a",
                        TenantLifecyclePolicy.AuthenticationState.ANONYMOUS,
                        Set.of(TenantLifecyclePolicy.Permission.DELETE_TENANT)),
                        resource, request, NOW));
        assertCode("ELMOS_MTF_AUTHENTICATION_EXPIRED", () ->
                TenantLifecyclePolicy.bind(new TenantLifecyclePolicy.AuthenticatedPrincipal(
                        "org-a", "account-a", "actor-authenticated",
                        TenantLifecyclePolicy.AuthenticationState.AUTHENTICATED,
                        AUTHENTICATED_AT, NOW,
                        Set.of(TenantLifecyclePolicy.Permission.DELETE_TENANT)),
                        resource, request, NOW));
        assertCode("ELMOS_MTF_RESOURCE_SCOPE_MISMATCH", () ->
                TenantLifecyclePolicy.bind(principal(
                        "org-a", "account-b",
                        TenantLifecyclePolicy.AuthenticationState.AUTHENTICATED,
                        Set.of(TenantLifecyclePolicy.Permission.DELETE_TENANT)),
                        resource, request, NOW));
        assertCode("ELMOS_MTF_LIFECYCLE_PERMISSION_DENIED", () ->
                TenantLifecyclePolicy.bind(principal(
                        "org-a", "account-a",
                        TenantLifecyclePolicy.AuthenticationState.AUTHENTICATED,
                        Set.of(TenantLifecyclePolicy.Permission.EXPORT_TENANT)),
                        resource, request, NOW));
    }

    @Test
    void boundActorAndResourceComeOnlyFromTrustedInputs() {
        var bound = TenantLifecyclePolicy.bind(principal(
                        "org-a", "account-a",
                        TenantLifecyclePolicy.AuthenticationState.AUTHENTICATED,
                        Set.of(TenantLifecyclePolicy.Permission.EXPORT_TENANT)),
                resource("org-a", "account-a", "tenant-authoritative"),
                new TenantLifecyclePolicy.LifecycleRequest(
                        "actor-attacker", "idem-a",
                        TenantLifecyclePolicy.Operation.EXPORT), NOW);

        assertEquals("actor-authenticated", bound.actorId());
        assertEquals("tenant-authoritative", bound.resourceId());
        assertNotEquals(bound.requestId(), bound.actorId());
    }

    @Test
    void exportPaginationAndManifestCountsAreExact() {
        var job = TenantLifecyclePolicy.requestJob(
                context(TenantLifecyclePolicy.Operation.EXPORT), "job-export", NOW);
        job = TenantLifecyclePolicy.beginExport(job, 0, NOW.plusSeconds(1));
        job = TenantLifecyclePolicy.appendExportPage(job, 1,
                new TenantLifecyclePolicy.PageResult(
                        2, DIGEST_A, "row-2", false), NOW.plusSeconds(2));
        job = TenantLifecyclePolicy.appendExportPage(job, 2,
                new TenantLifecyclePolicy.PageResult(
                        1, null, "row-3", true), NOW.plusSeconds(3));

        assertEquals(2, job.pageCheckpoint().pageNumber());
        assertEquals(3, job.pageCheckpoint().cumulativeRowCount());
        var terminal = job;
        assertCode("ELMOS_MTF_EXPORT_ALREADY_TERMINAL", () ->
                TenantLifecyclePolicy.appendExportPage(terminal, 3,
                        new TenantLifecyclePolicy.PageResult(
                                0, null, null, true), NOW.plusSeconds(4)));

        assertCode("ELMOS_MTF_EXPORT_MANIFEST_COUNT_MISMATCH", () ->
                TenantLifecyclePolicy.recordExportManifest(terminal, 3,
                        manifest(4, 2), NOW.plusSeconds(4)));

        var manifested = TenantLifecyclePolicy.recordExportManifest(terminal, 3,
                manifest(3, 2), NOW.plusSeconds(4));
        assertEquals(TenantLifecyclePolicy.JobState.LOCAL_MANIFEST_READY,
                manifested.state());
        assertEquals(DIGEST_B, manifested.exportManifest().contentDigest());
    }

    @Test
    void unknownOrNotRunObjectStorageResultNeverCompletesExport() {
        var job = exportReadyJob();
        job = TenantLifecyclePolicy.requestProviderOperation(job, job.version(),
                new TenantLifecyclePolicy.SecretReference(
                        "secret://tenant-export/object-store"),
                DIGEST_A, NOW.plusSeconds(5));

        var notRun = TenantLifecyclePolicy.observeProvider(job, job.version(),
                observation(TenantLifecyclePolicy.ProviderResult.NOT_RUN,
                        DIGEST_A, null), NOW.plusSeconds(6));
        assertEquals(TenantLifecyclePolicy.JobState.AWAITING_PROVIDER, notRun.state());

        var unknown = TenantLifecyclePolicy.observeProvider(notRun, notRun.version(),
                observation(TenantLifecyclePolicy.ProviderResult.UNKNOWN,
                        DIGEST_A, null), NOW.plusSeconds(7));
        assertEquals(TenantLifecyclePolicy.JobState.RECONCILING, unknown.state());

        var confirmed = TenantLifecyclePolicy.observeProvider(unknown, unknown.version(),
                observation(TenantLifecyclePolicy.ProviderResult.CONFIRMED,
                        DIGEST_A, DIGEST_B), NOW.plusSeconds(8));
        assertEquals(TenantLifecyclePolicy.JobState.COMPLETED, confirmed.state());
    }

    @Test
    void exportConfirmationMustBindTheLocalManifestDigest() {
        var job = exportReadyJob();
        job = TenantLifecyclePolicy.requestProviderOperation(job, job.version(),
                new TenantLifecyclePolicy.SecretReference("secret://export/key"),
                DIGEST_A, NOW.plusSeconds(5));
        var awaiting = job;

        assertCode("ELMOS_MTF_EXPORT_DIGEST_MISMATCH", () ->
                TenantLifecyclePolicy.observeProvider(awaiting, awaiting.version(),
                        observation(TenantLifecyclePolicy.ProviderResult.CONFIRMED,
                                DIGEST_A, DIGEST_C), NOW.plusSeconds(6)));
    }

    @Test
    void retentionLegalHoldAndUnknownPolicyBlockDeletion() {
        var requested = TenantLifecyclePolicy.requestJob(
                context(TenantLifecyclePolicy.Operation.DELETE), "job-delete", NOW);

        var held = TenantLifecyclePolicy.evaluateDeletion(requested, 0,
                guard(TenantLifecyclePolicy.LegalHoldState.ACTIVE,
                        TenantLifecyclePolicy.RetentionState.EXPIRED, null), NOW);
        assertEquals(TenantLifecyclePolicy.JobState.BLOCKED, held.state());
        assertEquals(TenantLifecyclePolicy.DeletionBlocker.LEGAL_HOLD,
                held.deletionBlocker());

        var retained = TenantLifecyclePolicy.evaluateDeletion(held, held.version(),
                guard(TenantLifecyclePolicy.LegalHoldState.CLEAR,
                        TenantLifecyclePolicy.RetentionState.ACTIVE,
                        NOW.plusSeconds(3600)), NOW.plusSeconds(1));
        assertEquals(TenantLifecyclePolicy.DeletionBlocker.RETENTION_ACTIVE,
                retained.deletionBlocker());

        var unknown = TenantLifecyclePolicy.evaluateDeletion(retained, retained.version(),
                guard(TenantLifecyclePolicy.LegalHoldState.UNKNOWN,
                        TenantLifecyclePolicy.RetentionState.UNKNOWN, null),
                NOW.plusSeconds(2));
        assertEquals(TenantLifecyclePolicy.DeletionBlocker.POLICY_UNKNOWN,
                unknown.deletionBlocker());
    }

    @Test
    void databaseTombstoneAndPhysicalPurgeRemainSeparateFacts() {
        var job = TenantLifecyclePolicy.requestJob(
                context(TenantLifecyclePolicy.Operation.DELETE), "job-delete", NOW);
        job = TenantLifecyclePolicy.evaluateDeletion(job, 0,
                guard(TenantLifecyclePolicy.LegalHoldState.CLEAR,
                        TenantLifecyclePolicy.RetentionState.EXPIRED,
                        NOW.minusSeconds(1)), NOW.plusSeconds(1));

        var tombstoning = job;
        assertCode("ELMOS_MTF_TOMBSTONE_UNPROVEN", () ->
                TenantLifecyclePolicy.recordDatabaseTombstone(tombstoning,
                        tombstoning.version(), tombstone(false, 1, "tenant-a"),
                        NOW.plusSeconds(2)));
        assertCode("ELMOS_MTF_TOMBSTONE_SCOPE_MISMATCH", () ->
                TenantLifecyclePolicy.recordDatabaseTombstone(tombstoning,
                        tombstoning.version(), tombstone(true, 1, "tenant-b"),
                        NOW.plusSeconds(2)));

        job = TenantLifecyclePolicy.recordDatabaseTombstone(job, job.version(),
                tombstone(true, 1, "tenant-a"), NOW.plusSeconds(2));
        assertEquals(TenantLifecyclePolicy.JobState.TOMBSTONED, job.state());

        job = TenantLifecyclePolicy.requestProviderOperation(job, job.version(),
                new TenantLifecyclePolicy.SecretReference("secret://purge/key"),
                DIGEST_A, NOW.plusSeconds(3));
        job = TenantLifecyclePolicy.observeProvider(job, job.version(),
                observation(TenantLifecyclePolicy.ProviderResult.UNKNOWN,
                        DIGEST_A, null), NOW.plusSeconds(4));
        assertEquals(TenantLifecyclePolicy.JobState.RECONCILING, job.state());
        assertEquals(true, job.tombstoneReceipt().transactionCommitted());
    }

    @Test
    void providerScopeRequestVersionAndSecretMaterialFailClosed() {
        var job = exportReadyJob();
        assertThrows(IllegalArgumentException.class, () ->
                new TenantLifecyclePolicy.SecretReference("raw-api-token"));
        assertThrows(IllegalArgumentException.class, () ->
                new TenantLifecyclePolicy.SecretReference(
                        "secret://export/key?token=plaintext"));
        assertCode("ELMOS_MTF_LIFECYCLE_VERSION_CONFLICT", () ->
                TenantLifecyclePolicy.requestProviderOperation(job, job.version() + 1,
                        new TenantLifecyclePolicy.SecretReference("secret://export/key"),
                        DIGEST_A, NOW.plusSeconds(5)));
    }

    @Test
    void csvFormulaCanaryAndHiddenPrefixesAreNeutralized() {
        assertEquals("\"'=1+1\"",
                TenantLifecyclePolicy.safeCsvCell(
                        TenantLifecyclePolicy.CSV_FORMULA_CANARY));
        assertEquals("\"'  @SUM(A1:A2)\"",
                TenantLifecyclePolicy.safeCsvCell("  @SUM(A1:A2)"));
        assertEquals("\"'\tcmd\"",
                TenantLifecyclePolicy.safeCsvCell("\tcmd"));
        assertEquals("\"safe, value\"",
                TenantLifecyclePolicy.safeCsvCell("safe, value"));
        assertEquals("\"say \"\"hello\"\"\"",
                TenantLifecyclePolicy.safeCsvCell("say \"hello\""));
    }

    private static TenantLifecyclePolicy.LifecycleJob exportReadyJob() {
        var job = TenantLifecyclePolicy.requestJob(
                context(TenantLifecyclePolicy.Operation.EXPORT), "job-export", NOW);
        job = TenantLifecyclePolicy.beginExport(job, 0, NOW.plusSeconds(1));
        job = TenantLifecyclePolicy.appendExportPage(job, 1,
                new TenantLifecyclePolicy.PageResult(
                        1, null, "row-1", true), NOW.plusSeconds(2));
        return TenantLifecyclePolicy.recordExportManifest(job, 2,
                manifest(1, 1), NOW.plusSeconds(3));
    }

    private static TenantLifecyclePolicy.AuthenticatedPrincipal principal(
            String organizationId,
            String accountId,
            TenantLifecyclePolicy.AuthenticationState authenticationState,
            Set<TenantLifecyclePolicy.Permission> permissions
    ) {
        return new TenantLifecyclePolicy.AuthenticatedPrincipal(
                organizationId, accountId, "actor-authenticated",
                authenticationState, AUTHENTICATED_AT, NOW.plusSeconds(3600),
                permissions);
    }

    private static TenantLifecyclePolicy.TrustedResourceBinding resource(
            String organizationId,
            String accountId,
            String resourceId
    ) {
        return new TenantLifecyclePolicy.TrustedResourceBinding(
                organizationId, accountId, resourceId);
    }

    private static TenantLifecyclePolicy.LifecycleRequest request(
            TenantLifecyclePolicy.Operation operation
    ) {
        return new TenantLifecyclePolicy.LifecycleRequest(
                "request-a", "idempotency-a", operation);
    }

    private static TenantLifecyclePolicy.BoundContext context(
            TenantLifecyclePolicy.Operation operation
    ) {
        TenantLifecyclePolicy.Permission permission =
                operation == TenantLifecyclePolicy.Operation.EXPORT
                        ? TenantLifecyclePolicy.Permission.EXPORT_TENANT
                        : TenantLifecyclePolicy.Permission.DELETE_TENANT;
        return TenantLifecyclePolicy.bind(principal(
                        "org-a", "account-a",
                        TenantLifecyclePolicy.AuthenticationState.AUTHENTICATED,
                        Set.of(permission)),
                resource("org-a", "account-a", "tenant-a"),
                request(operation), NOW);
    }

    private static TenantLifecyclePolicy.ExportManifest manifest(
            long rows,
            long pages
    ) {
        return new TenantLifecyclePolicy.ExportManifest(
                TenantLifecyclePolicy.ExportFormat.JSON, rows, pages,
                DIGEST_B, DIGEST_C, NOW.plusSeconds(4));
    }

    private static TenantLifecyclePolicy.DeletionGuard guard(
            TenantLifecyclePolicy.LegalHoldState hold,
            TenantLifecyclePolicy.RetentionState retention,
            Instant retainUntil
    ) {
        return new TenantLifecyclePolicy.DeletionGuard(
                hold, retention, retainUntil, DIGEST_B, NOW);
    }

    private static TenantLifecyclePolicy.DatabaseTombstoneReceipt tombstone(
            boolean committed,
            long rows,
            String resourceId
    ) {
        return new TenantLifecyclePolicy.DatabaseTombstoneReceipt(
                "tombstone-a", resourceId, DIGEST_C, rows, committed,
                NOW.plusSeconds(2));
    }

    private static TenantLifecyclePolicy.ProviderObservation observation(
            TenantLifecyclePolicy.ProviderResult result,
            String requestDigest,
            String resultDigest
    ) {
        boolean confirmed = result == TenantLifecyclePolicy.ProviderResult.CONFIRMED;
        return new TenantLifecyclePolicy.ProviderObservation(
                "observation-" + result.name().toLowerCase(), "tenant-a",
                requestDigest, result, confirmed ? "provider-object-a" : null,
                resultDigest, confirmed ? DIGEST_C : null, NOW.plusSeconds(6));
    }

    private static void assertCode(String code, Runnable action) {
        var error = assertThrows(TenantLifecyclePolicy.LifecycleException.class, action::run);
        assertEquals(code, error.code());
    }
}
