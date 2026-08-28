package io.elmos.workflow;

import java.time.Instant;
import java.util.Locale;
import java.util.Objects;
import java.util.Set;
import java.util.regex.Pattern;

/**
 * Pure policy for account-scoped tenant export and deletion jobs.
 *
 * <p>The policy deliberately keeps local database facts separate from external
 * provider facts. A local export manifest is not proof that an object was
 * delivered, and a committed database tombstone is not proof that replicas or
 * object storage were physically purged. Missing, pending, or unknown provider
 * observations therefore cannot complete a job.</p>
 */
public final class TenantLifecyclePolicy {
    public static final String CSV_FORMULA_CANARY = "=1+1";

    private static final int ID_MAX_LENGTH = 160;
    private static final Pattern IDENTIFIER = Pattern.compile(
            "[A-Za-z0-9][A-Za-z0-9._:@/\\-]{0,159}");
    private static final Pattern DIGEST = Pattern.compile("[a-f0-9]{64}");
    private static final Pattern SECRET_REFERENCE = Pattern.compile(
            "secret://[A-Za-z0-9][A-Za-z0-9._/\\-]{0,254}");

    public enum AuthenticationState {
        AUTHENTICATED,
        ANONYMOUS,
        UNKNOWN
    }

    public enum Permission {
        EXPORT_TENANT,
        DELETE_TENANT
    }

    public enum Operation {
        EXPORT,
        DELETE
    }

    public enum JobState {
        REQUESTED,
        ENUMERATING,
        LOCAL_MANIFEST_READY,
        TOMBSTONING,
        TOMBSTONED,
        BLOCKED,
        AWAITING_PROVIDER,
        RECONCILING,
        COMPLETED,
        FAILED
    }

    public enum ProviderResult {
        NOT_RUN,
        PENDING,
        CONFIRMED,
        FAILED,
        UNKNOWN
    }

    public enum LegalHoldState {
        CLEAR,
        ACTIVE,
        UNKNOWN
    }

    public enum RetentionState {
        EXPIRED,
        ACTIVE,
        UNKNOWN
    }

    public enum DeletionBlocker {
        NONE,
        LEGAL_HOLD,
        RETENTION_ACTIVE,
        POLICY_UNKNOWN
    }

    public enum ExportFormat {
        CSV,
        JSON
    }

    /** Stable boundary error; provider or database error text must not escape. */
    public static final class LifecycleException extends RuntimeException {
        private final String code;

        public LifecycleException(String code) {
            super(code);
            this.code = Objects.requireNonNull(code, "code");
        }

        public String code() {
            return code;
        }
    }

    /** Principal produced by the authentication layer, never request fields. */
    public record AuthenticatedPrincipal(
            String organizationId,
            String accountId,
            String actorId,
            AuthenticationState authenticationState,
            Instant authenticatedAt,
            Instant expiresAt,
            Set<Permission> permissions
    ) {
        public AuthenticatedPrincipal {
            organizationId = identifier(organizationId, "ORGANIZATION");
            accountId = identifier(accountId, "ACCOUNT");
            actorId = identifier(actorId, "ACTOR");
            Objects.requireNonNull(authenticationState, "authenticationState");
            Objects.requireNonNull(authenticatedAt, "authenticatedAt");
            Objects.requireNonNull(expiresAt, "expiresAt");
            if (!expiresAt.isAfter(authenticatedAt)) {
                throw new IllegalArgumentException("ELMOS_MTF_AUTH_WINDOW_INVALID");
            }
            permissions = Set.copyOf(Objects.requireNonNull(permissions, "permissions"));
        }
    }

    /** Resource ownership supplied by an authoritative tenant registry. */
    public record TrustedResourceBinding(
            String organizationId,
            String accountId,
            String resourceId
    ) {
        public TrustedResourceBinding {
            organizationId = identifier(organizationId, "ORGANIZATION");
            accountId = identifier(accountId, "ACCOUNT");
            resourceId = identifier(resourceId, "RESOURCE");
        }
    }

    /** Untrusted request metadata intentionally contains no tenant or actor. */
    public record LifecycleRequest(
            String requestId,
            String idempotencyKey,
            Operation operation
    ) {
        public LifecycleRequest {
            requestId = identifier(requestId, "REQUEST");
            idempotencyKey = identifier(idempotencyKey, "IDEMPOTENCY");
            Objects.requireNonNull(operation, "operation");
        }
    }

    /**
     * Scope that can only be created after authentication, authorization, and
     * trusted resource ownership all agree.
     */
    public static final class BoundContext {
        private final String organizationId;
        private final String accountId;
        private final String actorId;
        private final String resourceId;
        private final String requestId;
        private final String idempotencyKey;
        private final Operation operation;

        private BoundContext(
                AuthenticatedPrincipal principal,
                TrustedResourceBinding resource,
                LifecycleRequest request
        ) {
            this.organizationId = principal.organizationId();
            this.accountId = principal.accountId();
            this.actorId = principal.actorId();
            this.resourceId = resource.resourceId();
            this.requestId = request.requestId();
            this.idempotencyKey = request.idempotencyKey();
            this.operation = request.operation();
        }

        public String organizationId() {
            return organizationId;
        }

        public String accountId() {
            return accountId;
        }

        public String actorId() {
            return actorId;
        }

        public String resourceId() {
            return resourceId;
        }

        public String requestId() {
            return requestId;
        }

        public String idempotencyKey() {
            return idempotencyKey;
        }

        public Operation operation() {
            return operation;
        }
    }

    /** Opaque provider cursor is represented only by a digest. */
    public record PageResult(
            long rowCount,
            String nextCursorDigest,
            String lastResourceId,
            boolean terminal
    ) {
        public PageResult {
            if (rowCount < 0) {
                throw new IllegalArgumentException("ELMOS_MTF_PAGE_ROW_COUNT_INVALID");
            }
            nextCursorDigest = optionalDigest(nextCursorDigest, "CURSOR");
            lastResourceId = optionalIdentifier(lastResourceId, "LAST_RESOURCE");
            if (!terminal && nextCursorDigest == null) {
                throw new IllegalArgumentException("ELMOS_MTF_PAGE_CURSOR_REQUIRED");
            }
            if (rowCount > 0 && lastResourceId == null) {
                throw new IllegalArgumentException("ELMOS_MTF_PAGE_LAST_RESOURCE_REQUIRED");
            }
        }
    }

    public record PageCheckpoint(
            long pageNumber,
            long cumulativeRowCount,
            String cursorDigest,
            String lastResourceId,
            boolean terminal
    ) {
        public PageCheckpoint {
            if (pageNumber < 1 || cumulativeRowCount < 0) {
                throw new IllegalArgumentException("ELMOS_MTF_PAGE_CHECKPOINT_INVALID");
            }
            cursorDigest = optionalDigest(cursorDigest, "CURSOR");
            lastResourceId = optionalIdentifier(lastResourceId, "LAST_RESOURCE");
            if (!terminal && cursorDigest == null) {
                throw new IllegalArgumentException("ELMOS_MTF_PAGE_CURSOR_REQUIRED");
            }
        }
    }

    /** Content-addressed local export fact; it is not a delivery receipt. */
    public record ExportManifest(
            ExportFormat format,
            long rowCount,
            long pageCount,
            String contentDigest,
            String schemaDigest,
            Instant createdAt
    ) {
        public ExportManifest {
            Objects.requireNonNull(format, "format");
            if (rowCount < 0 || pageCount < 1) {
                throw new IllegalArgumentException("ELMOS_MTF_EXPORT_MANIFEST_INVALID");
            }
            contentDigest = digest(contentDigest, "EXPORT_CONTENT");
            schemaDigest = digest(schemaDigest, "EXPORT_SCHEMA");
            Objects.requireNonNull(createdAt, "createdAt");
        }
    }

    /** Only a locator is accepted; secret material is never part of this API. */
    public record SecretReference(String reference) {
        public SecretReference {
            if (reference == null || !SECRET_REFERENCE.matcher(reference).matches()
                    || reference.contains("..")) {
                throw new IllegalArgumentException("ELMOS_MTF_SECRET_REFERENCE_REQUIRED");
            }
        }
    }

    public record DeletionGuard(
            LegalHoldState legalHoldState,
            RetentionState retentionState,
            Instant retainUntil,
            String policyDigest,
            Instant evaluatedAt
    ) {
        public DeletionGuard {
            Objects.requireNonNull(legalHoldState, "legalHoldState");
            Objects.requireNonNull(retentionState, "retentionState");
            policyDigest = digest(policyDigest, "DELETION_POLICY");
            Objects.requireNonNull(evaluatedAt, "evaluatedAt");
            if (retentionState == RetentionState.ACTIVE && retainUntil == null) {
                throw new IllegalArgumentException("ELMOS_MTF_RETENTION_DEADLINE_REQUIRED");
            }
            if (retentionState == RetentionState.EXPIRED
                    && retainUntil != null && retainUntil.isAfter(evaluatedAt)) {
                throw new IllegalArgumentException("ELMOS_MTF_RETENTION_NOT_EXPIRED");
            }
        }
    }

    /** Committed local tombstone; no claim about physical provider deletion. */
    public record DatabaseTombstoneReceipt(
            String receiptId,
            String resourceId,
            String tombstoneDigest,
            long affectedRootRows,
            boolean transactionCommitted,
            Instant committedAt
    ) {
        public DatabaseTombstoneReceipt {
            receiptId = identifier(receiptId, "TOMBSTONE_RECEIPT");
            resourceId = identifier(resourceId, "RESOURCE");
            tombstoneDigest = digest(tombstoneDigest, "TOMBSTONE");
            if (affectedRootRows < 0) {
                throw new IllegalArgumentException("ELMOS_MTF_TOMBSTONE_ROW_COUNT_INVALID");
            }
            Objects.requireNonNull(committedAt, "committedAt");
        }
    }

    /** Provider observation; CONFIRMED alone has mandatory external evidence. */
    public record ProviderObservation(
            String observationId,
            String resourceId,
            String requestDigest,
            ProviderResult result,
            String providerReference,
            String resultDigest,
            String evidenceDigest,
            Instant observedAt
    ) {
        public ProviderObservation {
            observationId = identifier(observationId, "PROVIDER_OBSERVATION");
            resourceId = identifier(resourceId, "RESOURCE");
            requestDigest = digest(requestDigest, "PROVIDER_REQUEST");
            Objects.requireNonNull(result, "result");
            providerReference = optionalIdentifier(providerReference, "PROVIDER_REFERENCE");
            resultDigest = optionalDigest(resultDigest, "PROVIDER_RESULT");
            evidenceDigest = optionalDigest(evidenceDigest, "PROVIDER_EVIDENCE");
            Objects.requireNonNull(observedAt, "observedAt");
            if (result == ProviderResult.CONFIRMED
                    && (providerReference == null
                    || resultDigest == null
                    || evidenceDigest == null)) {
                throw new IllegalArgumentException("ELMOS_MTF_PROVIDER_EVIDENCE_REQUIRED");
            }
            if (result == ProviderResult.NOT_RUN
                    && (providerReference != null
                    || resultDigest != null
                    || evidenceDigest != null)) {
                throw new IllegalArgumentException("ELMOS_MTF_NOT_RUN_HAS_NO_EVIDENCE");
            }
        }
    }

    /** Immutable asynchronous job snapshot with optimistic versioning. */
    public static final class LifecycleJob {
        private final BoundContext context;
        private final String jobId;
        private final JobState state;
        private final long version;
        private final PageCheckpoint pageCheckpoint;
        private final ExportManifest exportManifest;
        private final DeletionBlocker deletionBlocker;
        private final DatabaseTombstoneReceipt tombstoneReceipt;
        private final String providerRequestDigest;
        private final SecretReference providerCredential;
        private final ProviderObservation providerObservation;
        private final Instant updatedAt;

        private LifecycleJob(
                BoundContext context,
                String jobId,
                JobState state,
                long version,
                PageCheckpoint pageCheckpoint,
                ExportManifest exportManifest,
                DeletionBlocker deletionBlocker,
                DatabaseTombstoneReceipt tombstoneReceipt,
                String providerRequestDigest,
                SecretReference providerCredential,
                ProviderObservation providerObservation,
                Instant updatedAt
        ) {
            this.context = Objects.requireNonNull(context, "context");
            this.jobId = identifier(jobId, "LIFECYCLE_JOB");
            this.state = Objects.requireNonNull(state, "state");
            if (version < 0) {
                throw new IllegalArgumentException("ELMOS_MTF_JOB_VERSION_INVALID");
            }
            this.version = version;
            this.pageCheckpoint = pageCheckpoint;
            this.exportManifest = exportManifest;
            this.deletionBlocker = Objects.requireNonNull(
                    deletionBlocker, "deletionBlocker");
            this.tombstoneReceipt = tombstoneReceipt;
            this.providerRequestDigest = optionalDigest(
                    providerRequestDigest, "PROVIDER_REQUEST");
            this.providerCredential = providerCredential;
            this.providerObservation = providerObservation;
            this.updatedAt = Objects.requireNonNull(updatedAt, "updatedAt");
        }

        public BoundContext context() {
            return context;
        }

        public String jobId() {
            return jobId;
        }

        public JobState state() {
            return state;
        }

        public long version() {
            return version;
        }

        public PageCheckpoint pageCheckpoint() {
            return pageCheckpoint;
        }

        public ExportManifest exportManifest() {
            return exportManifest;
        }

        public DeletionBlocker deletionBlocker() {
            return deletionBlocker;
        }

        public DatabaseTombstoneReceipt tombstoneReceipt() {
            return tombstoneReceipt;
        }

        public String providerRequestDigest() {
            return providerRequestDigest;
        }

        public SecretReference providerCredential() {
            return providerCredential;
        }

        public ProviderObservation providerObservation() {
            return providerObservation;
        }

        public Instant updatedAt() {
            return updatedAt;
        }
    }

    private TenantLifecyclePolicy() {}

    public static BoundContext bind(
            AuthenticatedPrincipal principal,
            TrustedResourceBinding resource,
            LifecycleRequest request,
            Instant now
    ) {
        Objects.requireNonNull(principal, "principal");
        Objects.requireNonNull(resource, "resource");
        Objects.requireNonNull(request, "request");
        Objects.requireNonNull(now, "now");
        if (principal.authenticationState() != AuthenticationState.AUTHENTICATED) {
            throw new LifecycleException("ELMOS_MTF_AUTHENTICATION_REQUIRED");
        }
        if (now.isBefore(principal.authenticatedAt()) || !now.isBefore(principal.expiresAt())) {
            throw new LifecycleException("ELMOS_MTF_AUTHENTICATION_EXPIRED");
        }
        if (!principal.organizationId().equals(resource.organizationId())
                || !principal.accountId().equals(resource.accountId())) {
            throw new LifecycleException("ELMOS_MTF_RESOURCE_SCOPE_MISMATCH");
        }
        Permission required = request.operation() == Operation.EXPORT
                ? Permission.EXPORT_TENANT : Permission.DELETE_TENANT;
        if (!principal.permissions().contains(required)) {
            throw new LifecycleException("ELMOS_MTF_LIFECYCLE_PERMISSION_DENIED");
        }
        return new BoundContext(principal, resource, request);
    }

    public static LifecycleJob requestJob(
            BoundContext context,
            String jobId,
            Instant requestedAt
    ) {
        return new LifecycleJob(context, jobId, JobState.REQUESTED, 0,
                null, null, DeletionBlocker.NONE, null,
                null, null, null, requestedAt);
    }

    public static LifecycleJob beginExport(
            LifecycleJob job,
            long expectedVersion,
            Instant startedAt
    ) {
        requireOperation(job, Operation.EXPORT);
        requireState(job, JobState.REQUESTED);
        return copy(job, expectedVersion, JobState.ENUMERATING,
                null, null, DeletionBlocker.NONE, null,
                null, null, null, startedAt);
    }

    public static LifecycleJob appendExportPage(
            LifecycleJob job,
            long expectedVersion,
            PageResult page,
            Instant checkpointedAt
    ) {
        requireOperation(job, Operation.EXPORT);
        requireState(job, JobState.ENUMERATING);
        Objects.requireNonNull(page, "page");
        PageCheckpoint previous = job.pageCheckpoint();
        if (previous != null && previous.terminal()) {
            throw new LifecycleException("ELMOS_MTF_EXPORT_ALREADY_TERMINAL");
        }
        long pageNumber = previous == null ? 1 : Math.addExact(previous.pageNumber(), 1);
        long previousRows = previous == null ? 0 : previous.cumulativeRowCount();
        long cumulativeRows = Math.addExact(previousRows, page.rowCount());
        PageCheckpoint checkpoint = new PageCheckpoint(
                pageNumber, cumulativeRows, page.nextCursorDigest(),
                page.lastResourceId(), page.terminal());
        return copy(job, expectedVersion, JobState.ENUMERATING,
                checkpoint, null, DeletionBlocker.NONE, null,
                null, null, null, checkpointedAt);
    }

    public static LifecycleJob recordExportManifest(
            LifecycleJob job,
            long expectedVersion,
            ExportManifest manifest,
            Instant recordedAt
    ) {
        requireOperation(job, Operation.EXPORT);
        requireState(job, JobState.ENUMERATING);
        Objects.requireNonNull(manifest, "manifest");
        PageCheckpoint checkpoint = job.pageCheckpoint();
        if (checkpoint == null || !checkpoint.terminal()) {
            throw new LifecycleException("ELMOS_MTF_EXPORT_PAGINATION_INCOMPLETE");
        }
        if (manifest.pageCount() != checkpoint.pageNumber()
                || manifest.rowCount() != checkpoint.cumulativeRowCount()) {
            throw new LifecycleException("ELMOS_MTF_EXPORT_MANIFEST_COUNT_MISMATCH");
        }
        return copy(job, expectedVersion, JobState.LOCAL_MANIFEST_READY,
                checkpoint, manifest, DeletionBlocker.NONE, null,
                null, null, null, recordedAt);
    }

    public static LifecycleJob evaluateDeletion(
            LifecycleJob job,
            long expectedVersion,
            DeletionGuard guard,
            Instant evaluatedAt
    ) {
        requireOperation(job, Operation.DELETE);
        requireAnyState(job, JobState.REQUESTED, JobState.BLOCKED);
        Objects.requireNonNull(guard, "guard");
        Objects.requireNonNull(evaluatedAt, "evaluatedAt");
        DeletionBlocker blocker = deletionBlocker(guard, evaluatedAt);
        JobState state = blocker == DeletionBlocker.NONE
                ? JobState.TOMBSTONING : JobState.BLOCKED;
        return copy(job, expectedVersion, state,
                null, null, blocker, null,
                null, null, null, evaluatedAt);
    }

    public static LifecycleJob recordDatabaseTombstone(
            LifecycleJob job,
            long expectedVersion,
            DatabaseTombstoneReceipt receipt,
            Instant recordedAt
    ) {
        requireOperation(job, Operation.DELETE);
        requireState(job, JobState.TOMBSTONING);
        Objects.requireNonNull(receipt, "receipt");
        if (!job.context().resourceId().equals(receipt.resourceId())) {
            throw new LifecycleException("ELMOS_MTF_TOMBSTONE_SCOPE_MISMATCH");
        }
        if (!receipt.transactionCommitted() || receipt.affectedRootRows() != 1) {
            throw new LifecycleException("ELMOS_MTF_TOMBSTONE_UNPROVEN");
        }
        return copy(job, expectedVersion, JobState.TOMBSTONED,
                null, null, DeletionBlocker.NONE, receipt,
                null, null, null, recordedAt);
    }

    public static LifecycleJob requestProviderOperation(
            LifecycleJob job,
            long expectedVersion,
            SecretReference credential,
            String requestDigest,
            Instant requestedAt
    ) {
        Objects.requireNonNull(credential, "credential");
        requestDigest = digest(requestDigest, "PROVIDER_REQUEST");
        if (job.context().operation() == Operation.EXPORT) {
            requireState(job, JobState.LOCAL_MANIFEST_READY);
        } else {
            requireState(job, JobState.TOMBSTONED);
        }
        return copy(job, expectedVersion, JobState.AWAITING_PROVIDER,
                job.pageCheckpoint(), job.exportManifest(), DeletionBlocker.NONE,
                job.tombstoneReceipt(), requestDigest, credential, null, requestedAt);
    }

    public static LifecycleJob observeProvider(
            LifecycleJob job,
            long expectedVersion,
            ProviderObservation observation,
            Instant recordedAt
    ) {
        requireAnyState(job, JobState.AWAITING_PROVIDER, JobState.RECONCILING);
        Objects.requireNonNull(observation, "observation");
        if (!job.context().resourceId().equals(observation.resourceId())) {
            throw new LifecycleException("ELMOS_MTF_PROVIDER_SCOPE_MISMATCH");
        }
        if (!Objects.equals(job.providerRequestDigest(), observation.requestDigest())) {
            throw new LifecycleException("ELMOS_MTF_PROVIDER_REQUEST_MISMATCH");
        }
        if (job.context().operation() == Operation.EXPORT
                && observation.result() == ProviderResult.CONFIRMED
                && !job.exportManifest().contentDigest().equals(observation.resultDigest())) {
            throw new LifecycleException("ELMOS_MTF_EXPORT_DIGEST_MISMATCH");
        }
        JobState state = switch (observation.result()) {
            case CONFIRMED -> JobState.COMPLETED;
            case FAILED -> JobState.FAILED;
            case UNKNOWN -> JobState.RECONCILING;
            case NOT_RUN, PENDING -> JobState.AWAITING_PROVIDER;
        };
        return copy(job, expectedVersion, state,
                job.pageCheckpoint(), job.exportManifest(), job.deletionBlocker(),
                job.tombstoneReceipt(), job.providerRequestDigest(),
                job.providerCredential(), observation, recordedAt);
    }

    /**
     * Serializes one CSV cell and neutralizes spreadsheet formula prefixes,
     * including prefixes hidden behind leading whitespace.
     */
    public static String safeCsvCell(String value) {
        Objects.requireNonNull(value, "value");
        String protectedValue = dangerousSpreadsheetPrefix(value) ? "'" + value : value;
        return "\"" + protectedValue.replace("\"", "\"\"") + "\"";
    }

    private static boolean dangerousSpreadsheetPrefix(String value) {
        int index = 0;
        while (index < value.length()) {
            int codePoint = value.codePointAt(index);
            if (codePoint == '\t' || codePoint == '\r') return true;
            if (!Character.isWhitespace(codePoint)) break;
            index += Character.charCount(codePoint);
        }
        if (index >= value.length()) return false;
        char prefix = value.charAt(index);
        return prefix == '=' || prefix == '+' || prefix == '-' || prefix == '@';
    }

    private static DeletionBlocker deletionBlocker(
            DeletionGuard guard,
            Instant evaluatedAt
    ) {
        if (guard.legalHoldState() == LegalHoldState.UNKNOWN
                || guard.retentionState() == RetentionState.UNKNOWN
                || guard.evaluatedAt().isAfter(evaluatedAt)) {
            return DeletionBlocker.POLICY_UNKNOWN;
        }
        if (guard.legalHoldState() == LegalHoldState.ACTIVE) {
            return DeletionBlocker.LEGAL_HOLD;
        }
        if (guard.retentionState() == RetentionState.ACTIVE
                && guard.retainUntil().isAfter(evaluatedAt)) {
            return DeletionBlocker.RETENTION_ACTIVE;
        }
        return DeletionBlocker.NONE;
    }

    private static LifecycleJob copy(
            LifecycleJob job,
            long expectedVersion,
            JobState state,
            PageCheckpoint checkpoint,
            ExportManifest manifest,
            DeletionBlocker blocker,
            DatabaseTombstoneReceipt tombstone,
            String providerRequestDigest,
            SecretReference providerCredential,
            ProviderObservation providerObservation,
            Instant updatedAt
    ) {
        requireVersion(job, expectedVersion);
        return new LifecycleJob(job.context(), job.jobId(), state,
                Math.addExact(job.version(), 1), checkpoint, manifest, blocker,
                tombstone, providerRequestDigest, providerCredential,
                providerObservation, updatedAt);
    }

    private static void requireVersion(LifecycleJob job, long expectedVersion) {
        Objects.requireNonNull(job, "job");
        if (job.version() != expectedVersion) {
            throw new LifecycleException("ELMOS_MTF_LIFECYCLE_VERSION_CONFLICT");
        }
    }

    private static void requireOperation(LifecycleJob job, Operation operation) {
        Objects.requireNonNull(job, "job");
        if (job.context().operation() != operation) {
            throw new LifecycleException("ELMOS_MTF_LIFECYCLE_OPERATION_MISMATCH");
        }
    }

    private static void requireState(LifecycleJob job, JobState state) {
        if (job.state() != state) {
            throw new LifecycleException("ELMOS_MTF_LIFECYCLE_STATE_CONFLICT");
        }
    }

    private static void requireAnyState(LifecycleJob job, JobState... states) {
        for (JobState state : states) {
            if (job.state() == state) return;
        }
        throw new LifecycleException("ELMOS_MTF_LIFECYCLE_STATE_CONFLICT");
    }

    private static String identifier(String value, String field) {
        if (value == null || value.length() > ID_MAX_LENGTH
                || !IDENTIFIER.matcher(value).matches()) {
            throw new IllegalArgumentException("ELMOS_MTF_" + field + "_INVALID");
        }
        return value;
    }

    private static String optionalIdentifier(String value, String field) {
        return value == null ? null : identifier(value, field);
    }

    private static String digest(String value, String field) {
        if (value == null || !DIGEST.matcher(value.toLowerCase(Locale.ROOT)).matches()) {
            throw new IllegalArgumentException("ELMOS_MTF_" + field + "_DIGEST_INVALID");
        }
        return value.toLowerCase(Locale.ROOT);
    }

    private static String optionalDigest(String value, String field) {
        return value == null ? null : digest(value, field);
    }
}
