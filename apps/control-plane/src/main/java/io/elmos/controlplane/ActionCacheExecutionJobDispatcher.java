package io.elmos.controlplane;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.cas.ActionCache;
import io.elmos.cas.ActionKey;
import io.elmos.cas.ActionKeyBuilder;
import io.elmos.cas.ActionResultRecord;
import io.elmos.cas.CasAccessPolicy;
import io.elmos.cas.CasDigest;
import io.elmos.cas.CasExceptions;
import io.elmos.workflow.ExecutionJobPort;

import java.math.BigDecimal;
import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.TreeMap;
import java.util.UUID;
import java.util.regex.Pattern;

/**
 * Asynchronous production adapter between a trusted {@link ActionCache} lookup and the durable
 * {@link ExecutionJobPort} queue.
 *
 * <p>A trusted cache hit is returned without creating a job. A miss or explicit bypass may be
 * enqueued only after a fresh EXECUTE authorization decision. Cache denial, unknown current
 * trust, cross-tenant execution, ambiguous authorization and queue uncertainty never become a
 * cache miss or a successful execution claim. The persisted request digest binds the exact action
 * key, trusted authorization grant, execution profile, immutable runner image, deployment-policy
 * sanitized payload and budget to the tenant-scoped idempotency key.</p>
 *
 * <p>The HTTP tenant binding constructs the canonical ActionKey and passes it here; this adapter
 * intentionally does not publish runner completion into the ActionCache.
 * {@link ExecutionJobPort.CompletionCommand} contains only terminal status and a failure code; it
 * has no signed {@link ActionResultRecord}, output manifest, producer context or attested writer.
 * Treating that completion as cacheable would manufacture trust. A future write-back path needs a
 * separate signed completion contract and durable persistence boundary.</p>
 *
 * <p>The queue payload carries the canonical request schema and SHA-256 plus a separately
 * auditable authorization decision ID. Reconciliation uses the queue's authoritative
 * tenant-scoped idempotency lookup and compares its persisted request digest before allowing a
 * retry. It still does not claim cross-instance runner completion or external trust evidence.</p>
 */
public final class ActionCacheExecutionJobDispatcher {

    private static final String CACHE_BINDING_FIELD = "_elmosActionCache";
    private static final String CANONICAL_DIGEST_FIELD = "_elmosCanonicalRequestSha256";
    private static final String CANONICAL_SCHEMA_FIELD = "_elmosCanonicalRequestSchema";
    private static final String AUTHORIZATION_AUDIT_FIELD = "_elmosAuthorizationAudit";
    private static final String CANONICAL_REQUEST_SCHEMA = "elmos-action-cache-dispatch/1";
    private static final int MAX_PAYLOAD_BYTES = 1024 * 1024;
    private static final int MAX_JSON_STRING_BYTES = 64 * 1024;
    private static final int MAX_JSON_DEPTH = 32;
    private static final int MAX_JSON_NODES = 10_000;
    private static final Pattern PINNED_IMAGE = Pattern.compile(
            "^[a-z0-9][a-z0-9._/-]*(:[0-9]+)?/?[a-z0-9._/-]*@sha256:[0-9a-f]{64}$");
    private static final Pattern DURABLE_JOB_ID = Pattern.compile(
            "^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$");
    private static final Pattern DECISION_REASON = Pattern.compile(
            "^[A-Z0-9][A-Z0-9._:-]{0,127}$");
    private static final Pattern SECRET_REFERENCE = Pattern.compile(
            "^secretref://[A-Za-z0-9][A-Za-z0-9._/-]{0,190}#[A-Za-z0-9][A-Za-z0-9._-]{0,63}$");
    private static final Pattern SENSITIVE_FIELD = Pattern.compile(
            ".*(authorization|password|secret|token|credential|api.?key).*");
    private static final String SECRET_REFERENCE_KIND = "ELMOS_SECRET_REFERENCE";
    private static final Set<String> RESERVED_PAYLOAD_FIELDS = Set.of(
            CACHE_BINDING_FIELD, CANONICAL_DIGEST_FIELD, CANONICAL_SCHEMA_FIELD,
            AUTHORIZATION_AUDIT_FIELD);
    private static final Set<String> COMPACT_DIGEST_ACTION_KEY_COMPONENTS = Set.of(
            "source_tree", "dependency_graph", "adapter", "rule_packs", "build_options",
            "command", "declared_outputs", "policy", "permission_scope", "sandbox",
            "environment");

    public enum Operation {
        CACHE_READ,
        EXECUTE
    }

    public enum AuthorizationStatus {
        ALLOW,
        DENY,
        UNKNOWN
    }

    public enum Mode {
        CACHE_ONLY,
        CACHE_OR_ENQUEUE
    }

    public enum OutcomeKind {
        CACHE_HIT,
        DURABLE_JOB_ACCEPTED,
        NOT_ENQUEUED,
        BLOCKED,
        UNKNOWN_RECONCILIATION_REQUIRED
    }

    /**
     * Identity and policy facts issued by the deployment-owned authorization boundary.
     *
     * <p>The dispatcher never derives queue identity from caller payload. It accepts these facts
     * only as part of an ALLOW decision returned by the configured {@link Authorizer}, validates
     * them against the reader, dispatch profile and immutable ActionKey, and then persists the
     * grant-derived tenant and actor.</p>
     */
    public record AuthorizationGrant(
            String tenantId,
            String actorId,
            String projectId,
            String decisionId,
            String policyVersion
    ) {
        public AuthorizationGrant {
            tenantId = boundedText(tenantId, 96, "authorization tenantId");
            actorId = boundedText(actorId, 128, "authorization actorId");
            projectId = boundedText(projectId, 128, "authorization projectId");
            decisionId = boundedMachineCode(decisionId, 128, "authorization decisionId");
            policyVersion = boundedMachineCode(
                    policyVersion, 128, "authorization policyVersion");
        }
    }

    public record AuthorizationDecision(
            AuthorizationStatus status,
            String reason,
            Optional<AuthorizationGrant> grant
    ) {
        public AuthorizationDecision {
            Objects.requireNonNull(status, "status");
            reason = boundedDecisionReason(reason);
            grant = Objects.requireNonNull(grant, "grant");
            if ((status == AuthorizationStatus.ALLOW) != grant.isPresent()) {
                throw new IllegalArgumentException(
                        "exactly an ALLOW authorization decision must carry a trusted grant");
            }
        }

        public static AuthorizationDecision allow(
                String reason, AuthorizationGrant grant
        ) {
            return new AuthorizationDecision(
                    AuthorizationStatus.ALLOW, reason, Optional.of(grant));
        }

        public static AuthorizationDecision deny(String reason) {
            return new AuthorizationDecision(
                    AuthorizationStatus.DENY, reason, Optional.empty());
        }

        public static AuthorizationDecision unknown(String reason) {
            return new AuthorizationDecision(
                    AuthorizationStatus.UNKNOWN, reason, Optional.empty());
        }
    }

    /** A Secret Reference is an opaque, version-bound locator, never secret material. */
    public record SecretReference(String opaqueReference) {
        public SecretReference {
            opaqueReference = boundedText(opaqueReference, 256, "secret opaqueReference");
            if (!SECRET_REFERENCE.matcher(opaqueReference).matches()) {
                throw new IllegalArgumentException(
                        "secret reference must be an opaque version-bound secretref URI");
            }
        }
    }

    /**
     * Immutable execution profile passed to the existing durable queue.
     *
     * <p>The organization is deliberately absent: it is derived from the reader context after the
     * deployment-owned Authorizer binds that context to authenticated identity. Execution is
     * allowed only when the resulting tenant also owns the ActionKey.</p>
     */
    public record DispatchSpec(
            String actorId,
            ExecutionJobPort.BusinessLine businessLine,
            String jobKind,
            String idempotencyKey,
            Map<String, Object> payload,
            String requiredCapability,
            String runnerImage,
            short priority,
            int budgetWallSeconds,
            short maxAttempts,
            String accountId,
            String requestId,
            String workloadClass,
            int resourceUnits
    ) {
        public DispatchSpec(
                String actorId,
                ExecutionJobPort.BusinessLine businessLine,
                String jobKind,
                String idempotencyKey,
                Map<String, Object> payload,
                String requiredCapability,
                String runnerImage,
                short priority,
                int budgetWallSeconds,
                short maxAttempts
        ) {
            this(actorId, businessLine, jobKind, idempotencyKey, payload,
                    requiredCapability, runnerImage, priority, budgetWallSeconds,
                    maxAttempts, "", "", defaultWorkloadClass(businessLine),
                    defaultResourceUnits(businessLine));
        }

        public DispatchSpec {
            actorId = boundedText(actorId, 128, "actorId");
            accountId = optionalBoundedText(accountId, 96, "accountId");
            requestId = optionalBoundedText(requestId, 160, "requestId");
            workloadClass = boundedMachineCode(
                    workloadClass == null || workloadClass.isBlank()
                            ? "GENERATION" : workloadClass,
                    32, "workloadClass");
            if (!Set.of("PARSING", "GENERATION", "CONVERSION", "VALIDATION",
                    "RENDERING", "MODEL_GPU").contains(workloadClass)
                    || resourceUnits < 1 || resourceUnits > 64) {
                throw new IllegalArgumentException("workload profile is invalid");
            }
            Objects.requireNonNull(businessLine, "businessLine");
            jobKind = boundedText(jobKind, 64, "jobKind");
            idempotencyKey = boundedText(idempotencyKey, 160, "idempotencyKey");
            payload = immutableRawJsonObject(payload);
            validateRawSensitivePayload(payload);
            rejectReservedPayloadFields(payload);
            requiredCapability = boundedText(requiredCapability, 96, "requiredCapability");
            runnerImage = boundedText(runnerImage, 255, "runnerImage");
            if (!PINNED_IMAGE.matcher(runnerImage).matches()) {
                throw new IllegalArgumentException("runnerImage must be pinned by sha256 digest");
            }
            if (priority < 1 || priority > 1000) {
                throw new IllegalArgumentException("priority must be between 1 and 1000");
            }
            if (budgetWallSeconds < 60 || budgetWallSeconds > 43_200) {
                throw new IllegalArgumentException(
                        "budgetWallSeconds must be between 60 and 43200");
            }
            if (maxAttempts != 1) {
                throw new IllegalArgumentException(
                        "maxAttempts must be exactly 1 for ActionCache dispatch");
            }
        }

        private static String defaultWorkloadClass(ExecutionJobPort.BusinessLine line) {
            return switch (Objects.requireNonNull(line, "businessLine")) {
                case GENERATION -> "GENERATION";
                case TRANSLATION, SPRING_UPGRADE -> "CONVERSION";
                case REPOSITORY_WORKSPACE -> "PARSING";
                case MODERNIZATION_PROOF -> "VALIDATION";
            };
        }

        private static int defaultResourceUnits(ExecutionJobPort.BusinessLine line) {
            return switch (Objects.requireNonNull(line, "businessLine")) {
                case GENERATION, MODERNIZATION_PROOF -> 2;
                case TRANSLATION, SPRING_UPGRADE -> 3;
                case REPOSITORY_WORKSPACE -> 1;
            };
        }
    }

    /**
     * A reconciliation retry supplies the exact digest returned by the uncertain first attempt.
     * The dispatcher refuses to enqueue when the newly materialized stable subject differs and
     * preserves that first digest in an UNKNOWN_RECONCILIATION_REQUIRED outcome. Drift cannot turn
     * an unresolved enqueue into either a fresh side effect or a deterministic failure claim.
     */
    public record Request(
            ActionKey key,
            CasAccessPolicy.ReaderContext reader,
            DispatchSpec dispatch,
            boolean bypassCache,
            Mode mode,
            Optional<CasDigest> expectedPriorRequestDigest
    ) {
        public Request {
            Objects.requireNonNull(key, "key");
            Objects.requireNonNull(reader, "reader");
            Objects.requireNonNull(dispatch, "dispatch");
            Objects.requireNonNull(mode, "mode");
            expectedPriorRequestDigest = Objects.requireNonNull(
                    expectedPriorRequestDigest, "expectedPriorRequestDigest");
            String keyedImage = key.components().get("toolchain_image");
            if (!dispatch.runnerImage().equals(keyedImage)) {
                throw new IllegalArgumentException(
                        "runnerImage must equal the immutable toolchain_image in the ActionKey");
            }
            boundedText(key.components().get("project_id"), 128,
                    "ActionKey project_id");
        }

        public Request(
                ActionKey key,
                CasAccessPolicy.ReaderContext reader,
                DispatchSpec dispatch,
                boolean bypassCache,
                Mode mode
        ) {
            this(key, reader, dispatch, bypassCache, mode, Optional.empty());
        }
    }

    /** Input to a deployment-owned, typed and allowlisted payload policy. */
    public record PayloadContext(Request request, AuthorizationGrant authorization) {
        public PayloadContext {
            Objects.requireNonNull(request, "request");
            Objects.requireNonNull(authorization, "authorization");
        }
    }

    /**
     * Canonical payload returned by the deployment policy. Its constructor deep-copies,
     * Unicode-normalizes and canonicalizes all values; raw caller maps are never persisted.
     */
    public record SanitizedPayload(
            String policyId,
            String policyVersion,
            Map<String, Object> payload
    ) {
        public SanitizedPayload {
            policyId = boundedMachineCode(policyId, 128, "payload policyId");
            policyVersion = boundedMachineCode(
                    policyVersion, 128, "payload policyVersion");
            payload = immutableCanonicalJsonObject(payload);
            rejectReservedPayloadFields(payload);
            validateSanitizedSensitivePayload(payload);
        }
    }

    public record Outcome(
            OutcomeKind kind,
            String reason,
            Optional<ActionResultRecord> result,
            Optional<String> jobId,
            Optional<CasDigest> requestDigest,
            Optional<ActionCache.CacheOutcome> cacheOutcome,
            boolean idempotentReplay
    ) {
        public Outcome {
            Objects.requireNonNull(kind, "kind");
            reason = boundedText(reason, 512, "reason");
            result = Objects.requireNonNull(result, "result");
            jobId = Objects.requireNonNull(jobId, "jobId");
            requestDigest = Objects.requireNonNull(requestDigest, "requestDigest");
            cacheOutcome = Objects.requireNonNull(cacheOutcome, "cacheOutcome");
            if ((kind == OutcomeKind.CACHE_HIT) != result.isPresent()) {
                throw new IllegalArgumentException("only CACHE_HIT may carry an ActionResult");
            }
            if ((kind == OutcomeKind.DURABLE_JOB_ACCEPTED) != jobId.isPresent()) {
                throw new IllegalArgumentException(
                        "only DURABLE_JOB_ACCEPTED may carry a jobId");
            }
            if ((kind == OutcomeKind.DURABLE_JOB_ACCEPTED
                    || kind == OutcomeKind.UNKNOWN_RECONCILIATION_REQUIRED)
                    != requestDigest.isPresent()) {
                throw new IllegalArgumentException(
                        "accepted or uncertain queue outcomes must carry the exact request digest");
            }
            if (kind == OutcomeKind.CACHE_HIT
                    && cacheOutcome.filter(value -> value == ActionCache.CacheOutcome.HIT)
                    .isEmpty()) {
                throw new IllegalArgumentException("CACHE_HIT requires the cache HIT outcome");
            }
            if (idempotentReplay && kind != OutcomeKind.DURABLE_JOB_ACCEPTED) {
                throw new IllegalArgumentException(
                        "only an accepted durable job can be an idempotent replay");
            }
        }

        public boolean cacheResultSucceeded() {
            return result.filter(value -> value.status() == ActionResultRecord.Status.SUCCEEDED)
                    .isPresent();
        }

        private static Outcome blocked(
                String reason, Optional<ActionCache.CacheOutcome> cacheOutcome
        ) {
            return new Outcome(OutcomeKind.BLOCKED, reason, Optional.empty(), Optional.empty(),
                    Optional.empty(), cacheOutcome, false);
        }
    }

    @FunctionalInterface
    public interface Authorizer {
        AuthorizationDecision authorize(Request request, Operation operation);
    }

    /**
     * Deployment-owned allowlist/sanitizer. Implementations must return only the fields and typed
     * Secret References accepted for the selected job kind; returning the raw input is not a
     * substitute for an allowlist.
     */
    @FunctionalInterface
    public interface PayloadPolicy {
        SanitizedPayload sanitize(PayloadContext context);
    }

    private final ActionCache cache;
    private final ExecutionJobPort jobs;
    private final Authorizer authorizer;
    private final PayloadPolicy payloadPolicy;

    public ActionCacheExecutionJobDispatcher(
            ActionCache cache,
            ExecutionJobPort jobs,
            Authorizer authorizer,
            PayloadPolicy payloadPolicy
    ) {
        this.cache = Objects.requireNonNull(cache, "cache");
        this.jobs = Objects.requireNonNull(jobs, "jobs");
        this.authorizer = Objects.requireNonNull(authorizer, "authorizer");
        this.payloadPolicy = Objects.requireNonNull(payloadPolicy, "payloadPolicy");
    }

    /**
     * Compatibility/testing constructor proving that application ObjectMapper settings cannot
     * influence the private canonical digest encoding.
     */
    ActionCacheExecutionJobDispatcher(
            ActionCache cache,
            ExecutionJobPort jobs,
            Authorizer authorizer,
            PayloadPolicy payloadPolicy,
            ObjectMapper ignoredApplicationJson
    ) {
        this(cache, jobs, authorizer, payloadPolicy);
        Objects.requireNonNull(ignoredApplicationJson, "ignoredApplicationJson");
    }

    public Outcome dispatch(Request request) {
        Objects.requireNonNull(request, "request");
        ReconciliationGuard reconciliation = ReconciliationGuard.forRequest(request);
        try {
            verifyCanonicalActionKey(request.key());
        } catch (RuntimeException forgedOrIncomplete) {
            return reconciliation.blockedOrPending(
                    "ACTION_KEY_INVALID", Optional.empty());
        }
        // This must precede authorization and every cache operation. Otherwise a cross-tenant
        // caller could distinguish an existing key from a miss through lookup outcomes.
        if (!request.key().tenantId().equals(request.reader().tenantId())) {
            return reconciliation.blockedOrPending(
                    "REQUEST_TENANT_MISMATCH", Optional.empty());
        }
        if (request.bypassCache()) {
            ActionCache.Lookup bypass;
            try {
                bypass = Objects.requireNonNull(
                        cache.get(request.key(), request.reader(), true),
                        "cache bypass outcome");
            } catch (RuntimeException unavailable) {
                return reconciliation.blockedOrPending(
                        "CACHE_BYPASS_RECORD_UNAVAILABLE", Optional.empty());
            }
            return enqueueAfterAuthorization(
                    request, Optional.of(bypass.outcome()), bypass.reason());
        }

        AuthorizationDecision cacheRead = authorize(request, Operation.CACHE_READ);
        Optional<String> cacheAuthorizationFailure = authorizationFailure(
                request, Operation.CACHE_READ, cacheRead);
        if (cacheAuthorizationFailure.isPresent()) {
            return reconciliation.blockedOrPending(
                    cacheAuthorizationFailure.orElseThrow(), Optional.empty());
        }

        ActionCache.Lookup lookup;
        try {
            lookup = Objects.requireNonNull(
                    cache.get(request.key(), request.reader(), false),
                    "cache lookup outcome");
        } catch (CasExceptions.CasAccessDeniedException denied) {
            return reconciliation.blockedOrPending(
                    "CACHE_ACCESS_DENIED:" + denied.reason(), Optional.empty());
        } catch (RuntimeException unavailable) {
            return reconciliation.blockedOrPending(
                    "CACHE_LOOKUP_UNAVAILABLE", Optional.empty());
        }
        if (lookup.outcome() == ActionCache.CacheOutcome.HIT) {
            Outcome hit = new Outcome(OutcomeKind.CACHE_HIT, lookup.reason(), lookup.result(),
                    Optional.empty(), Optional.empty(), Optional.of(lookup.outcome()), false);
            return reconciliation.ordinaryOrPending(
                    hit, "CACHE_HIT_IS_NOT_QUEUE_RECONCILIATION",
                    Optional.of(lookup.outcome()));
        }
        if (lookup.outcome() == ActionCache.CacheOutcome.DENIED) {
            return reconciliation.blockedOrPending(
                    "CACHE_LOOKUP_DENIED:" + lookup.reason(),
                    Optional.of(lookup.outcome()));
        }
        return enqueueAfterAuthorization(
                request, Optional.of(lookup.outcome()), lookup.reason());
    }

    private Outcome enqueueAfterAuthorization(
            Request request,
            Optional<ActionCache.CacheOutcome> cacheOutcome,
            String cacheReason
    ) {
        ReconciliationGuard reconciliation = ReconciliationGuard.forRequest(request);
        if (request.mode() == Mode.CACHE_ONLY) {
            Outcome cacheOnly = new Outcome(
                    OutcomeKind.NOT_ENQUEUED, "CACHE_ONLY:" + cacheReason,
                    Optional.empty(), Optional.empty(), Optional.empty(), cacheOutcome, false);
            return reconciliation.ordinaryOrPending(
                    cacheOnly, "CACHE_ONLY_IS_NOT_QUEUE_RECONCILIATION", cacheOutcome);
        }
        AuthorizationDecision execution = authorize(request, Operation.EXECUTE);
        Optional<String> executionAuthorizationFailure = authorizationFailure(
                request, Operation.EXECUTE, execution);
        if (executionAuthorizationFailure.isPresent()) {
            return reconciliation.blockedOrPending(
                    executionAuthorizationFailure.orElseThrow(), cacheOutcome);
        }
        AuthorizationGrant grant = execution.grant().orElseThrow();
        DispatchSpec spec = request.dispatch();
        if (spec.accountId().isBlank() || spec.requestId().isBlank()) {
            return reconciliation.blockedOrPending(
                    "EXECUTION_IDENTITY_CONTEXT_REQUIRED", cacheOutcome);
        }

        DispatchMaterial material;
        try {
            material = materialize(request, grant);
        } catch (RuntimeException invalid) {
            return reconciliation.blockedOrPending(
                    "DISPATCH_REQUEST_INVALID", cacheOutcome);
        }
        if (reconciliation.isPending()
                && !reconciliation.subject().equals(material.digest())) {
            // The first enqueue may already have committed. Material drift under the same
            // idempotency key therefore remains UNKNOWN and must never become a fresh enqueue or a
            // deterministic rejection. Preserve the first attempt's digest as the only subject a
            // reconciler is allowed to inspect.
            return reconciliation.pending(
                    "RECONCILIATION_MATERIAL_DRIFT_NO_QUEUE_RETRY",
                    cacheOutcome);
        }
        if (reconciliation.isPending()) {
            Optional<ExecutionJobPort.IdempotencyLookup> existing;
            try {
                existing = Objects.requireNonNull(
                        jobs.findByIdempotencyKey(
                                new ExecutionJobPort.AuthenticatedContext(
                                        grant.tenantId(), spec.accountId(),
                                        grant.actorId(), spec.requestId()),
                                spec.idempotencyKey()),
                        "idempotency lookup result");
            } catch (RuntimeException unavailable) {
                return reconciliation.pending(
                        "RECONCILIATION_IDEMPOTENCY_LOOKUP_UNAVAILABLE", cacheOutcome);
            }
            if (existing.isPresent()) {
                ExecutionJobPort.IdempotencyLookup persisted = existing.orElseThrow();
                if (!reconciliation.subject().hex().equals(persisted.requestDigest())) {
                    return reconciliation.pending(
                            "RECONCILIATION_PERSISTED_REQUEST_DIGEST_MISMATCH",
                            cacheOutcome);
                }
                if (!DURABLE_JOB_ID.matcher(persisted.jobId()).matches()) {
                    return reconciliation.pending(
                            "RECONCILIATION_PERSISTED_JOB_ID_INVALID", cacheOutcome);
                }
                return new Outcome(
                        OutcomeKind.DURABLE_JOB_ACCEPTED,
                        "DURABLE_JOB_RECONCILED",
                        Optional.empty(),
                        Optional.of(persisted.jobId()),
                        Optional.of(reconciliation.subject()),
                        cacheOutcome,
                        true);
            }
            // No row exists for the exact tenant/idempotency key at this authoritative read point.
            // Reusing the same key and digest is safe: the database unique constraint makes a
            // concurrent first commit return its original job instead of creating a duplicate.
        }

        String requestedJobId = "job-" + UUID.randomUUID();
        String persisted;
        try {
                persisted = jobs.enqueue(new ExecutionJobPort.EnqueueCommand(
                    requestedJobId,
                    grant.tenantId(),
                    spec.accountId(),
                    grant.actorId(),
                    spec.businessLine(),
                    spec.jobKind(),
                    spec.idempotencyKey(),
                    material.digest().hex(),
                    material.payload(),
                    spec.requiredCapability(),
                    spec.runnerImage(),
                    spec.priority(),
                    spec.budgetWallSeconds(),
                    (short) 1,
                    spec.requestId(),
                    spec.workloadClass(),
                    spec.resourceUnits()));
        } catch (ExecutionJobPort.ExecutionStateException rejected) {
            if ("ELMOS_EXECUTION_IDEMPOTENCY_CONFLICT".equals(rejected.code())) {
                return reconciliation.uncertainQueueOutcome(
                        "QUEUE_IDEMPOTENCY_CONFLICT_RECONCILIATION_REQUIRED",
                        material.digest(), cacheOutcome);
            }
            // A typed rejection still crosses the durable queue boundary. Unless the port returns
            // an authoritative persisted job identity, the adapter cannot prove that no commit
            // happened immediately before the exception was observed.
            return reconciliation.uncertainQueueOutcome(
                    "QUEUE_REJECTED_RECONCILIATION_REQUIRED",
                    material.digest(), cacheOutcome);
        } catch (RuntimeException unavailable) {
            return reconciliation.uncertainQueueOutcome(
                    "QUEUE_OUTCOME_UNKNOWN_RETRY_WITH_EXPECTED_PRIOR_REQUEST_DIGEST",
                    material.digest(), cacheOutcome);
        }
        if (persisted == null || !DURABLE_JOB_ID.matcher(persisted).matches()) {
            return reconciliation.uncertainQueueOutcome(
                    "QUEUE_RETURNED_INVALID_JOB_ID_RECONCILE_WITH_PRIOR_REQUEST_DIGEST",
                    material.digest(), cacheOutcome);
        }
        return new Outcome(OutcomeKind.DURABLE_JOB_ACCEPTED,
                persisted.equals(requestedJobId)
                        ? "DURABLE_JOB_ENQUEUED"
                        : "DURABLE_JOB_IDEMPOTENT_REPLAY",
                Optional.empty(), Optional.of(persisted), Optional.of(material.digest()),
                cacheOutcome, !persisted.equals(requestedJobId));
    }

    private AuthorizationDecision authorize(Request request, Operation operation) {
        try {
            AuthorizationDecision decision = authorizer.authorize(request, operation);
            return decision == null
                    ? AuthorizationDecision.unknown("AUTHORIZER_RETURNED_NO_DECISION")
                    : decision;
        } catch (RuntimeException unavailable) {
            return AuthorizationDecision.unknown("AUTHORIZATION_PROVIDER_UNAVAILABLE");
        }
    }

    private DispatchMaterial materialize(Request request, AuthorizationGrant grant) {
        DispatchSpec spec = request.dispatch();
        SanitizedPayload sanitized = payloadPolicy.sanitize(
                new PayloadContext(request, grant));
        if (sanitized == null) {
            throw new IllegalArgumentException("payload policy returned no decision");
        }
        Map<String, Object> cacheBinding = new LinkedHashMap<>();
        cacheBinding.put("schemaVersion", "1.0");
        cacheBinding.put("actionKeySchema", ActionKeyBuilder.CANONICAL_SCHEMA);
        cacheBinding.put("actionKeyDigest", request.key().digest().hex());
        cacheBinding.put("actionKeyTenantId", request.key().tenantId());
        cacheBinding.put("actionKeyProjectId", grant.projectId());
        // Preserve the complete identity for a future signed completion write-back. The digest is
        // sufficient for lookup, but a runner result must reconstruct and re-verify every
        // canonical component before it can ever become cacheable.
        // Components are copied into the immutable canonical payload below; callers cannot
        // mutate the queued identity.
        cacheBinding.put("actionKeyComponents", request.key().components());
        cacheBinding.put("authorizationPolicyVersion", grant.policyVersion());
        cacheBinding.put("payloadPolicyId", sanitized.policyId());
        cacheBinding.put("payloadPolicyVersion", sanitized.policyVersion());
        Map<String, Object> stablePayload = new LinkedHashMap<>(sanitized.payload());
        stablePayload.put(CACHE_BINDING_FIELD, cacheBinding);
        Map<String, Object> immutableStablePayload =
                immutableCanonicalJsonObject(stablePayload);

        Map<String, Object> digestSubject = new LinkedHashMap<>();
        digestSubject.put("schemaVersion", CANONICAL_REQUEST_SCHEMA);
        digestSubject.put("organizationId", grant.tenantId());
        digestSubject.put("accountId", spec.accountId());
        digestSubject.put("actorId", grant.actorId());
        digestSubject.put("projectId", grant.projectId());
        digestSubject.put("authorizationPolicyVersion", grant.policyVersion());
        digestSubject.put("businessLine", spec.businessLine().name());
        digestSubject.put("jobKind", spec.jobKind());
        digestSubject.put("idempotencyKey", spec.idempotencyKey());
        digestSubject.put("requestPayload", immutableStablePayload);
        digestSubject.put("requiredCapability", spec.requiredCapability());
        digestSubject.put("runnerImage", spec.runnerImage());
        digestSubject.put("priority", spec.priority());
        digestSubject.put("budgetWallSeconds", spec.budgetWallSeconds());
        digestSubject.put("maxAttempts", spec.maxAttempts());
        digestSubject.put("workloadClass", spec.workloadClass());
        digestSubject.put("resourceUnits", spec.resourceUnits());
        byte[] canonical = canonicalJsonBytes(digestSubject);
        if (canonical.length > MAX_PAYLOAD_BYTES) {
            throw new IllegalArgumentException(
                    "canonical dispatch request exceeds " + MAX_PAYLOAD_BYTES + " bytes");
        }
        CasDigest requestDigest = CasDigest.of(canonical);
        Map<String, Object> persistedPayload = new LinkedHashMap<>(immutableStablePayload);
        persistedPayload.put(CANONICAL_SCHEMA_FIELD, CANONICAL_REQUEST_SCHEMA);
        persistedPayload.put(CANONICAL_DIGEST_FIELD, requestDigest.hex());
        persistedPayload.put(AUTHORIZATION_AUDIT_FIELD, Map.of(
                "decisionId", grant.decisionId(),
                "policyVersion", grant.policyVersion()));
        return new DispatchMaterial(
                immutableCanonicalJsonObject(persistedPayload), requestDigest);
    }

    private record DispatchMaterial(Map<String, Object> payload, CasDigest digest) {
    }

    /**
     * One guard owns every outcome emitted while an earlier enqueue is unresolved. It prevents a
     * cache result, authorization denial, local validation failure or queue exception from erasing
     * the original reconciliation subject, and it makes a second enqueue impossible without an
     * explicit authoritative lookup contract.
     */
    private record ReconciliationGuard(Optional<CasDigest> expectedPriorRequestDigest) {

        private ReconciliationGuard {
            Objects.requireNonNull(expectedPriorRequestDigest, "expectedPriorRequestDigest");
        }

        private static ReconciliationGuard forRequest(Request request) {
            return new ReconciliationGuard(request.expectedPriorRequestDigest());
        }

        private boolean isPending() {
            return expectedPriorRequestDigest.isPresent();
        }

        private CasDigest subject() {
            return expectedPriorRequestDigest.orElseThrow();
        }

        private Outcome pending(
                String reason, Optional<ActionCache.CacheOutcome> cacheOutcome
        ) {
            return new Outcome(OutcomeKind.UNKNOWN_RECONCILIATION_REQUIRED,
                    reason, Optional.empty(), Optional.empty(),
                    Optional.of(subject()), cacheOutcome, false);
        }

        private Outcome blockedOrPending(
                String blockedReason, Optional<ActionCache.CacheOutcome> cacheOutcome
        ) {
            return isPending()
                    ? pending("RECONCILIATION_PENDING:" + blockedReason, cacheOutcome)
                    : Outcome.blocked(blockedReason, cacheOutcome);
        }

        private Outcome ordinaryOrPending(
                Outcome ordinary,
                String reconciliationReason,
                Optional<ActionCache.CacheOutcome> cacheOutcome
        ) {
            return isPending() ? pending(reconciliationReason, cacheOutcome) : ordinary;
        }

        private Outcome uncertainQueueOutcome(
                String reason,
                CasDigest currentRequestDigest,
                Optional<ActionCache.CacheOutcome> cacheOutcome
        ) {
            CasDigest subject = expectedPriorRequestDigest.orElse(currentRequestDigest);
            return new Outcome(OutcomeKind.UNKNOWN_RECONCILIATION_REQUIRED,
                    reason, Optional.empty(), Optional.empty(), Optional.of(subject),
                    cacheOutcome, false);
        }
    }

    private static String authorizationReason(
            Operation operation, AuthorizationDecision decision
    ) {
        return operation.name() + "_AUTHORIZATION_" + decision.status().name()
                + ":" + decision.reason();
    }

    private static Optional<String> authorizationFailure(
            Request request, Operation operation, AuthorizationDecision decision
    ) {
        if (decision.status() != AuthorizationStatus.ALLOW) {
            return Optional.of(authorizationReason(operation, decision));
        }
        AuthorizationGrant grant = decision.grant().orElseThrow();
        String projectId = request.key().components().get("project_id");
        if (!grant.tenantId().equals(request.reader().tenantId())
                || !grant.tenantId().equals(request.key().tenantId())
                || !grant.actorId().equals(request.dispatch().actorId())
                || !grant.projectId().equals(projectId)) {
            return Optional.of(operation.name() + "_AUTHORIZATION_GRANT_MISMATCH");
        }
        return Optional.empty();
    }

    /** Shared v2 identity verification plus this dispatch boundary's stricter value/size limits. */
    private static void verifyCanonicalActionKey(ActionKey key) {
        ActionKeyBuilder.verifyCanonical(key);
        Map<String, String> components = key.components();
        int[] byteCount = new int[]{0};
        accountActionKeyFieldSize(byteCount, ActionKeyBuilder.CANONICAL_SCHEMA);
        for (Map.Entry<String, String> component : components.entrySet()) {
            String name = component.getKey();
            String value = component.getValue();
            validateActionKeyText(name, false);
            validateActionKeyText(value,
                    "prompt".equals(name) || "model".equals(name));
            validateActionKeyComponent(name, value);
            accountActionKeyFieldSize(byteCount, name);
            accountActionKeyFieldSize(byteCount, value);
        }
    }

    private static void validateActionKeyText(String value, boolean emptyAllowed) {
        if (value == null || (!emptyAllowed && value.isBlank()) || value.indexOf('\0') >= 0
                || value.getBytes(StandardCharsets.UTF_8).length > MAX_JSON_STRING_BYTES) {
            throw new IllegalArgumentException("ActionKey text is invalid or oversized");
        }
    }

    private static void validateActionKeyComponent(String name, String value) {
        if (COMPACT_DIGEST_ACTION_KEY_COMPONENTS.contains(name)) {
            CasDigest.parseCompact(value);
        } else if (("prompt".equals(name) || "model".equals(name))
                && !value.isEmpty()) {
            CasDigest.parseCompact(value);
        } else if ("toolchain_image".equals(name)
                && !PINNED_IMAGE.matcher(value).matches()) {
            throw new IllegalArgumentException("ActionKey toolchain image is not immutable");
        }
    }

    private static void accountActionKeyFieldSize(int[] byteCount, String value) {
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        String prefix = bytes.length + ":";
        int addition = prefix.getBytes(StandardCharsets.UTF_8).length + bytes.length + 1;
        if (byteCount[0] > MAX_PAYLOAD_BYTES - addition) {
            throw new IllegalArgumentException("ActionKey canonical form exceeds limit");
        }
        byteCount[0] += addition;
    }

    private static String boundedText(String value, int maximum, String field) {
        String candidate = value == null ? "" : normalizeUnicode(value.trim());
        if (candidate.isEmpty() || candidate.length() > maximum
                || candidate.getBytes(StandardCharsets.UTF_8).length > maximum * 4) {
            throw new IllegalArgumentException(field + " is missing or exceeds " + maximum);
        }
        for (int index = 0; index < candidate.length(); index++) {
            if (Character.isISOControl(candidate.charAt(index))) {
                throw new IllegalArgumentException(field + " contains control characters");
            }
        }
        return candidate;
    }

    private static String optionalBoundedText(String value, int maximum, String field) {
        if (value == null || value.isBlank()) {
            return "";
        }
        return boundedText(value, maximum, field);
    }

    private static String boundedMachineCode(String value, int maximum, String field) {
        String candidate = boundedText(value, maximum, field);
        for (int index = 0; index < candidate.length(); index++) {
            char character = candidate.charAt(index);
            if (!(character >= 'A' && character <= 'Z')
                    && !(character >= 'a' && character <= 'z')
                    && !(character >= '0' && character <= '9')
                    && "._:/@-".indexOf(character) < 0) {
                throw new IllegalArgumentException(field + " must be a stable machine code");
            }
        }
        return candidate;
    }

    private static Map<String, Object> immutableRawJsonObject(Map<String, Object> source) {
        return immutableJsonObject(source, false);
    }

    private static Map<String, Object> immutableCanonicalJsonObject(
            Map<String, Object> source
    ) {
        return immutableJsonObject(source, true);
    }

    private static Map<String, Object> immutableJsonObject(
            Map<String, Object> source, boolean canonical
    ) {
        Objects.requireNonNull(source, "payload");
        @SuppressWarnings("unchecked")
        Map<String, Object> copy = (Map<String, Object>) immutableJsonValue(
                source, 0, new TraversalBudget(), canonical);
        return copy;
    }

    private static Object immutableJsonValue(
            Object value, int depth, TraversalBudget budget, boolean canonical
    ) {
        if (depth > MAX_JSON_DEPTH) {
            throw new IllegalArgumentException(
                    "payload nesting exceeds " + MAX_JSON_DEPTH);
        }
        budget.addNode();
        if (value == null) {
            budget.addUtf8("null");
            return value;
        }
        if (value instanceof Boolean bool) {
            budget.addUtf8(bool ? "true" : "false");
            return value;
        }
        if (value instanceof Byte || value instanceof Short || value instanceof Integer
                || value instanceof Long) {
            budget.addUtf8(value.toString());
            return value;
        }
        if (value instanceof String string) {
            String normalized = jsonString(string);
            budget.addUtf8(normalized);
            return normalized;
        }
        if (value instanceof BigInteger integer) {
            if (integer.bitLength() > 8_192) {
                throw new IllegalArgumentException("payload integer exceeds canonical bounds");
            }
            budget.addUtf8(integer.toString());
            return integer;
        }
        if (value instanceof BigDecimal decimal) {
            if (decimal.precision() > 16_384
                    || Math.abs((long) decimal.scale()) > 16_384L) {
                throw new IllegalArgumentException("payload decimal exceeds canonical bounds");
            }
            BigDecimal normalized = decimal.signum() == 0
                    ? BigDecimal.ZERO : decimal.stripTrailingZeros();
            String encoded = normalized.toPlainString();
            if (encoded.getBytes(StandardCharsets.UTF_8).length > MAX_JSON_STRING_BYTES) {
                throw new IllegalArgumentException("payload decimal exceeds canonical bounds");
            }
            budget.addUtf8(encoded);
            return normalized;
        }
        if (value instanceof Float || value instanceof Double) {
            throw new IllegalArgumentException(
                    "floating point payload values are prohibited; use BigDecimal");
        }
        if (value instanceof SecretReference reference) {
            if (!canonical) {
                budget.addUtf8(reference.opaqueReference());
                return reference;
            }
            return immutableJsonValue(
                    Map.of(
                            "kind", SECRET_REFERENCE_KIND,
                            "opaqueReference", reference.opaqueReference()),
                    depth + 1,
                    budget,
                    true);
        }
        if (value instanceof Map<?, ?> map) {
            budget.addStructuralBytes(2);
            Map<String, Object> nested = canonical ? new TreeMap<>() : new LinkedHashMap<>();
            for (Map.Entry<?, ?> entry : map.entrySet()) {
                Object key = entry.getKey();
                if (!(key instanceof String stringKey)) {
                    throw new IllegalArgumentException("payload object keys must be strings");
                }
                String normalizedKey = jsonKey(stringKey);
                budget.addUtf8(normalizedKey);
                budget.addStructuralBytes(3);
                if (nested.containsKey(normalizedKey)) {
                    throw new IllegalArgumentException(
                            "payload contains duplicate keys after Unicode normalization");
                }
                nested.put(normalizedKey,
                        immutableJsonValue(entry.getValue(), depth + 1, budget, canonical));
            }
            return Collections.unmodifiableMap(nested);
        }
        if (value instanceof List<?> list) {
            budget.addStructuralBytes(2);
            List<Object> nested = new ArrayList<>();
            list.forEach(item -> nested.add(
                    immutableJsonValue(item, depth + 1, budget, canonical)));
            return Collections.unmodifiableList(nested);
        }
        throw new IllegalArgumentException(
                "payload values must be JSON primitives, objects or arrays");
    }

    private static String jsonKey(String value) {
        String normalized = value == null ? "" : normalizeUnicode(value);
        if (normalized.isBlank() || normalized.length() > 256
                || normalized.getBytes(StandardCharsets.UTF_8).length > 1024) {
            throw new IllegalArgumentException("payload key is missing or exceeds 256");
        }
        for (int index = 0; index < normalized.length(); index++) {
            if (Character.isISOControl(normalized.charAt(index))) {
                throw new IllegalArgumentException("payload key contains control characters");
            }
        }
        return normalized;
    }

    private static String jsonString(String value) {
        if (value.length() > MAX_JSON_STRING_BYTES
                || value.getBytes(StandardCharsets.UTF_8).length > MAX_JSON_STRING_BYTES) {
            throw new IllegalArgumentException("payload string exceeds canonical bounds");
        }
        String normalized = normalizeUnicode(value);
        if (normalized.getBytes(StandardCharsets.UTF_8).length > MAX_JSON_STRING_BYTES) {
            throw new IllegalArgumentException("payload string exceeds canonical bounds");
        }
        return normalized;
    }

    private static String boundedDecisionReason(String value) {
        String candidate = value == null ? "" : value.trim();
        if (!DECISION_REASON.matcher(candidate).matches()) {
            throw new IllegalArgumentException(
                    "authorization reason must be a stable machine-readable code");
        }
        return candidate;
    }

    private static void rejectReservedPayloadFields(Map<String, Object> payload) {
        for (String reserved : RESERVED_PAYLOAD_FIELDS) {
            if (payload.containsKey(reserved)) {
                throw new IllegalArgumentException(
                        reserved + " is reserved for the verified ActionCache envelope");
            }
        }
    }

    private static void validateRawSensitivePayload(Object value) {
        if (value instanceof Map<?, ?> map) {
            for (Map.Entry<?, ?> entry : map.entrySet()) {
                String key = String.valueOf(entry.getKey()).toLowerCase(Locale.ROOT);
                if (SENSITIVE_FIELD.matcher(key).matches()
                        && !(entry.getValue() instanceof SecretReference)) {
                    throw new IllegalArgumentException(
                            "sensitive payload values must be typed SecretReference objects");
                }
                validateRawSensitivePayload(entry.getValue());
            }
        } else if (value instanceof List<?> list) {
            list.forEach(ActionCacheExecutionJobDispatcher::validateRawSensitivePayload);
        }
    }

    private static void validateSanitizedSensitivePayload(Object value) {
        if (value instanceof Map<?, ?> map) {
            for (Map.Entry<?, ?> entry : map.entrySet()) {
                String key = String.valueOf(entry.getKey()).toLowerCase(Locale.ROOT);
                if (SENSITIVE_FIELD.matcher(key).matches()) {
                    if (!isCanonicalSecretReference(entry.getValue())) {
                        throw new IllegalArgumentException(
                                "sensitive sanitized values must be typed SecretReferences");
                    }
                } else {
                    validateSanitizedSensitivePayload(entry.getValue());
                }
            }
        } else if (value instanceof List<?> list) {
            list.forEach(
                    ActionCacheExecutionJobDispatcher::validateSanitizedSensitivePayload);
        }
    }

    private static boolean isCanonicalSecretReference(Object value) {
        if (!(value instanceof Map<?, ?> reference) || reference.size() != 2) {
            return false;
        }
        return SECRET_REFERENCE_KIND.equals(reference.get("kind"))
                && reference.get("opaqueReference") instanceof String opaque
                && SECRET_REFERENCE.matcher(opaque).matches();
    }

    private static String normalizeUnicode(String value) {
        Objects.requireNonNull(value, "text");
        for (int index = 0; index < value.length(); index++) {
            char character = value.charAt(index);
            if (Character.isHighSurrogate(character)) {
                if (index + 1 >= value.length()
                        || !Character.isLowSurrogate(value.charAt(index + 1))) {
                    throw new IllegalArgumentException("text contains an unpaired surrogate");
                }
                index++;
            } else if (Character.isLowSurrogate(character)) {
                throw new IllegalArgumentException("text contains an unpaired surrogate");
            }
        }
        return Normalizer.normalize(value, Normalizer.Form.NFC);
    }

    private static byte[] canonicalJsonBytes(Object value) {
        CanonicalJsonWriter output = new CanonicalJsonWriter();
        appendCanonicalJson(value, output);
        return output.bytes();
    }

    private static void appendCanonicalJson(Object value, CanonicalJsonWriter output) {
        if (value == null) {
            output.append("null");
        } else if (value instanceof String string) {
            appendCanonicalJsonString(normalizeUnicode(string), output);
        } else if (value instanceof Boolean bool) {
            output.append(bool ? "true" : "false");
        } else if (value instanceof Byte || value instanceof Short
                || value instanceof Integer || value instanceof Long
                || value instanceof BigInteger) {
            output.append(value.toString());
        } else if (value instanceof BigDecimal decimal) {
            BigDecimal normalized = decimal.signum() == 0
                    ? BigDecimal.ZERO : decimal.stripTrailingZeros();
            output.append(normalized.toPlainString());
        } else if (value instanceof Map<?, ?> map) {
            output.append('{');
            boolean first = true;
            Map<String, Object> sorted = new TreeMap<>();
            for (Map.Entry<?, ?> entry : map.entrySet()) {
                if (!(entry.getKey() instanceof String key)) {
                    throw new IllegalArgumentException("canonical JSON map key is not a string");
                }
                sorted.put(normalizeUnicode(key), entry.getValue());
            }
            for (Map.Entry<String, Object> entry : sorted.entrySet()) {
                if (!first) {
                    output.append(',');
                }
                first = false;
                appendCanonicalJsonString(entry.getKey(), output);
                output.append(':');
                appendCanonicalJson(entry.getValue(), output);
            }
            output.append('}');
        } else if (value instanceof List<?> list) {
            output.append('[');
            boolean first = true;
            for (Object item : list) {
                if (!first) {
                    output.append(',');
                }
                first = false;
                appendCanonicalJson(item, output);
            }
            output.append(']');
        } else {
            throw new IllegalArgumentException("value is not canonical JSON");
        }
    }

    private static void appendCanonicalJsonString(
            String value, CanonicalJsonWriter output
    ) {
        output.append('"');
        for (int index = 0; index < value.length(); index++) {
            char character = value.charAt(index);
            switch (character) {
                case '"' -> output.append("\\\"");
                case '\\' -> output.append("\\\\");
                case '\b' -> output.append("\\b");
                case '\f' -> output.append("\\f");
                case '\n' -> output.append("\\n");
                case '\r' -> output.append("\\r");
                case '\t' -> output.append("\\t");
                default -> {
                    if (character < 0x20) {
                        output.append(String.format(Locale.ROOT, "\\u%04x", (int) character));
                    } else if (Character.isHighSurrogate(character)) {
                        output.append(value.substring(index, index + 2));
                        index++;
                    } else {
                        output.append(character);
                    }
                }
            }
        }
        output.append('"');
    }

    private static final class CanonicalJsonWriter {
        private final StringBuilder output = new StringBuilder();
        private int utf8Bytes;

        private void append(char value) {
            append(String.valueOf(value));
        }

        private void append(String value) {
            int added = value.getBytes(StandardCharsets.UTF_8).length;
            if (utf8Bytes > MAX_PAYLOAD_BYTES - added) {
                throw new IllegalArgumentException(
                        "canonical dispatch request exceeds " + MAX_PAYLOAD_BYTES + " bytes");
            }
            utf8Bytes += added;
            output.append(value);
        }

        private byte[] bytes() {
            return output.toString().getBytes(StandardCharsets.UTF_8);
        }
    }

    /** Bounds the immutable-copy phase before it can duplicate an oversized caller graph. */
    private static final class TraversalBudget {
        private int nodes;
        private int utf8Bytes;

        private void addNode() {
            nodes++;
            if (nodes > MAX_JSON_NODES) {
                throw new IllegalArgumentException(
                        "payload node count exceeds " + MAX_JSON_NODES);
            }
        }

        private void addUtf8(String value) {
            addStructuralBytes(value.getBytes(StandardCharsets.UTF_8).length);
        }

        private void addStructuralBytes(int added) {
            if (added < 0 || utf8Bytes > MAX_PAYLOAD_BYTES - added) {
                throw new IllegalArgumentException(
                        "payload immutable copy exceeds " + MAX_PAYLOAD_BYTES + " bytes");
            }
            utf8Bytes += added;
        }
    }
}
