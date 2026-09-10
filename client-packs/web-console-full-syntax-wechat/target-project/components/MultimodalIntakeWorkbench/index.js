// Top-level helpers and constants
try { const chunkBytes = 256 * 1024; } catch(e) {}
try { const maximumProcessableAssetBytes = 64 * 1024 * 1024; } catch(e) {}
try { const maximumBatchAssets = 256; } catch(e) {}
try { const maximumBatchBytes = 512 * 1024 * 1024; } catch(e) {}
try { const maximumSkillResponseBytes = 4 * 1024 * 1024; } catch(e) {}
try { const maximumReviewQueueTasks = 10_000; } catch(e) {}
try { const maximumReviewQueuePages = 50; } catch(e) {}
try { const maximumReviewSources = 1_000; } catch(e) {}
try { const maximumReviewSourcePages = 5; } catch(e) {}
try { const maximumStoredReviewClaims = 100; } catch(e) {}
try { const maximumStoredReviewEnqueueAttempts = 100; } catch(e) {}
try { const reviewClaimLeaseSeconds = 900; } catch(e) {}
try { const skillRequestTimeoutMs = 60_000; } catch(e) {}
try { const pendingReviewClaimRecoveryMs = (reviewClaimLeaseSeconds * 1000
    + skillRequestTimeoutMs
    + 2 * 60 * 1000); } catch(e) {}
try { const webBffRoute = "/api/multimodal-intake/v1/execute"; } catch(e) {}
try { const browserRequestSchemaVersion = "multimodal-intake-browser-request-v1"; } catch(e) {}
try { const recoveryDatabaseName = "elmos-multimodal-intake-recovery-v1"; } catch(e) {}
try { const recoveryStoreName = "upload-recovery"; } catch(e) {}
try { const recoveryRecordKeys = new Set([
    "schemaVersion",
    "identityScope",
    "fileFingerprint",
    "expectedSize",
    "lastModified",
    "partSize",
    "attemptKey",
    "projectId",
    "engineProjectId",
    "sessionAttemptKey",
    "contentSha256",
    "sessionId",
    "uploadSessionId",
    "confirmedPartCount",
    "processingAttempt",
    "assetId",
    "assetVersion",
    "role",
    "modelReadAllowed",
    "updatedAt",
]); } catch(e) {}
try { const legacyReviewClaimStorageKey = "elmos-multimodal-review-claims-v1"; } catch(e) {}
try { const reviewClaimStoragePrefix = "elmos-multimodal-review-claims-v2"; } catch(e) {}
try { const legacyReviewEnqueueStoragePrefix = "elmos-multimodal-review-enqueue-v1"; } catch(e) {}
try { const reviewEnqueueStoragePrefix = "elmos-multimodal-review-enqueue-v2"; } catch(e) {}
try { const reviewClaimKeys = new Set([
    "schema_version",
    "identity_scope",
    "project_id",
    "task_id",
    "token",
    "idempotency_key",
    "expected_version",
    "created_at",
    "fence",
    "expires_at",
]); } catch(e) {}
try { const reviewEnqueueAttemptKeys = new Set([
    "schema_version",
    "identity_scope",
    "project_scope_digest",
    "request_digest",
    "recovery_handle",
    "prepare_idempotency_key",
    "execute_idempotency_key",
    "created_at",
]); } catch(e) {}
try { const reviewSourceEnqueueInputKeys = new Set([
    "content_id", "expected_asset_version", "target_kind", "target_digest",
    "expected_head_version", "expected_snapshot_id", "expected_snapshot_digest",
    "expected_head_value_digest", "original_value_digest", "reason",
]); } catch(e) {}
try { const reviewEnqueuePreparationFields = new Set([
    "schema_version", "recovery_handle", "request_digest", "state", "safe_to_clear",
    "expires_at", "prepared_at", "executed_at", "task_id", "enqueue_input",
]); } catch(e) {}
try { const reviewEnqueuePreparationAbsenceFields = new Set([
    "schema_version", "recovery_handle", "state", "safe_to_clear",
]); } catch(e) {}
try { const reviewTaskStates = new Set([
    "QUEUED", "CLAIMED", "EDITED", "APPROVED", "REJECTED", "REOPENED",
    "REVERTING", "REVERTED",
]); } catch(e) {}
try { const reviewTaskFullFields = new Set([
    "task_id", "tenant_id", "project_id", "asset_id", "target_kind", "target",
    "original_value", "source_digest", "source_ref", "confidence", "reason", "state",
    "current_correction_version", "current_correction_digest", "effective_version",
    "effective_digest", "claim_actor_id", "claim_fence", "claim_expires_at", "version",
    "created_by", "created_at", "updated_at", "closed_at",
]); } catch(e) {}
try { const reviewTaskSummaryFields = new Set([
    "schema_version", "task_id", "asset_id", "target_kind", "source_digest", "confidence",
    "reason", "state", "current_correction_version", "current_correction_digest",
    "effective_version", "effective_digest", "claim_actor_id", "claim_fence",
    "claim_expires_at", "version", "created_at", "updated_at", "closed_at",
]); } catch(e) {}
try { const reviewSourceRefFields = new Set([
    "schema_version", "content_id", "content_version", "content_digest", "asset_sha256",
    "target_kind", "target_digest", "snapshot_id", "snapshot_digest", "head_version",
    "head_value_digest", "source_digest", "provenance_digest",
    "original_value_client_digest", "original_value_digest_contract",
]); } catch(e) {}
try { const reviewSourceSummaryFields = new Set([
    "schema_version", "content_id", "content_version", "target_kind", "target",
    "target_digest", "confidence", "head_version", "head_direction",
    "head_correction_version", "original_value_client_digest",
    "original_value_digest_contract", "source_ref",
]); } catch(e) {}
try { const reviewSourceDetailFields = new Set([...reviewSourceSummaryFields, "original_value"]); } catch(e) {}
try { const reviewCorrectionFields = new Set([
    "correction_id", "tenant_id", "project_id", "task_id", "correction_version",
    "parent_correction_version", "target_kind", "target", "original_value",
    "corrected_value", "source_digest", "actor_id", "reason", "created_at",
    "correction_digest",
]); } catch(e) {}
try { const reviewDecisionFields = new Set([
    "decision_id", "tenant_id", "project_id", "task_id", "decision_version",
    "decision", "prior_state", "next_state", "correction_version",
    "correction_digest", "source_digest", "actor_id", "reason", "created_at",
]); } catch(e) {}
try { const reviewPropagationSummaryFields = new Set([
    "propagation_id", "task_id", "decision_id", "correction_version", "channel",
    "direction", "payload_digest", "effective_value_digest", "state", "claim_fence",
    "claim_expires_at", "dispatch_started_at", "failure_code", "reconciliation_required",
    "version", "updated_at",
]); } catch(e) {}
try { const reviewEffectiveFields = new Set([
    "materialized", "state", "effective_version", "effective_value",
    "effective_value_digest", "channels",
]); } catch(e) {}
try { const reviewEffectiveChannelFields = new Set([
    "channel", "source_decision_id", "correction_version", "direction",
    "effective_value_digest", "version", "updated_at",
]); } catch(e) {}
try { const supportedExtensions = new Set([
    "txt", "md", "markdown", "mdx", "log", "pdf", "doc", "docx",
    "png", "jpg", "jpeg", "webp", "heic", "tiff", "bmp", "svg",
    "mp3", "wav", "m4a", "aac", "flac", "ogg", "opus",
    "zip", "tar", "tar.gz", "gz", "tgz",
]); } catch(e) {}
try { function safeProject(value) {
    return /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(value);
} } catch(e) {}
try { function relativePath(file) {
    const candidate = file.webkitRelativePath || file.name;
    return candidate.replaceAll("\\", "/").replace(/^\/+/, "");
} } catch(e) {}
try { function extensionOf(file) {
    const suffixes = file.name.toLocaleLowerCase("en-US").split(".");
    if (suffixes.length > 2 && suffixes.slice(-2).join(".") === "tar.gz")
        return "tar.gz";
    return suffixes.length > 1 ? suffixes.at(-1) ?? "" : "";
} } catch(e) {}
try { function bytesToBase64(bytes) {
    let binary = "";
    for (let offset = 0; offset < bytes.length; offset += 0x8000) {
        binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
    }
    return btoa(binary);
} } catch(e) {}
try { async function sha256(buffer) {
    const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", buffer));
    return [...digest].map((byte) => byte.toString(16).padStart(2, "0")).join("");
} } catch(e) {}
try { async function fingerprintFile(file) {
    const identity = `${relativePath(file)}\u0000${file.size}\u0000${file.lastModified}`;
    return sha256(new TextEncoder().encode(identity).buffer);
} } catch(e) {}
try { const fileHashWorkerSource = `
self.onmessage = async (event) => {
  try {
    const file = event.data;
    const bytes = await file.arrayBuffer();
    const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
    const value = Array.from(digest, (byte) => byte.toString(16).padStart(2, "0")).join("");
    self.postMessage({ ok: true, digest: value });
  } catch (_error) {
    self.postMessage({ ok: false });
  }
};
`; } catch(e) {}
try { async function sha256FileOffMainThread(file) {
    if (typeof Worker === "undefined" || typeof URL.createObjectURL !== "function") {
        throw new Error("FILE_HASH_WORKER_UNAVAILABLE");
    }
    const workerUrl = URL.createObjectURL(new Blob([fileHashWorkerSource], { type: "text/javascript" }));
    let worker;
    try {
        const activeWorker = new Worker(workerUrl);
        worker = activeWorker;
        return await new Promise((resolve, reject) => {
            activeWorker.onmessage = (event) => {
                const digest = event.data?.digest;
                if (event.data?.ok === true && typeof digest === "string" && /^[0-9a-f]{64}$/.test(digest)) {
                    resolve(digest);
                    return;
                }
                reject(new Error("FILE_HASH_WORKER_FAILED"));
            };
            activeWorker.onerror = () => reject(new Error("FILE_HASH_WORKER_FAILED"));
            activeWorker.onmessageerror = () => reject(new Error("FILE_HASH_WORKER_FAILED"));
            activeWorker.postMessage(file);
        });
    }
    finally {
        worker?.terminate();
        URL.revokeObjectURL(workerUrl);
    }
} } catch(e) {}
try { function boundedOpaque(value) {
    return typeof value === "string"
        && value.length > 0
        && value.length <= 512
        && !/[\u0000-\u001f\u007f]/.test(value);
} } catch(e) {}
try { function reviewClaimStorageKey(identityScope) {
    return `${reviewClaimStoragePrefix}:${identityScope}`;
} } catch(e) {}
try { function reviewEnqueueStorageKey(identityScope) {
    return `${reviewEnqueueStoragePrefix}:${identityScope}`;
} } catch(e) {}
try { function structurallyValidReviewEnqueueAttempt(value) {
    if (!value || typeof value !== "object" || Array.isArray(value))
        return false;
    const attempt = value;
    return Object.keys(attempt).length === reviewEnqueueAttemptKeys.size
        && Object.keys(attempt).every((key) => reviewEnqueueAttemptKeys.has(key))
        && attempt.schema_version === 3
        && typeof attempt.identity_scope === "string"
        && /^sha256:[0-9a-f]{64}$/.test(attempt.identity_scope)
        && typeof attempt.project_scope_digest === "string"
        && /^sha256:[0-9a-f]{64}$/.test(attempt.project_scope_digest)
        && typeof attempt.request_digest === "string"
        && /^sha256:[0-9a-f]{64}$/.test(attempt.request_digest)
        && typeof attempt.recovery_handle === "string"
        && /^mmi-review-recovery-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(attempt.recovery_handle)
        && typeof attempt.prepare_idempotency_key === "string"
        && /^mmi-review-enqueue-prepare-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(attempt.prepare_idempotency_key)
        && typeof attempt.execute_idempotency_key === "string"
        && /^mmi-review-enqueue-execute-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(attempt.execute_idempotency_key)
        && attempt.prepare_idempotency_key !== attempt.execute_idempotency_key
        && typeof attempt.created_at === "number"
        && Number.isSafeInteger(attempt.created_at)
        && attempt.created_at >= 0
        && attempt.created_at <= Date.now() + 60_000;
} } catch(e) {}
try { function structurallyValidReviewSourceEnqueueInput(value) {
    if (!value || typeof value !== "object" || Array.isArray(value))
        return false;
    const input = value;
    const targetKind = input.target_kind;
    return exactObjectFields(input, reviewSourceEnqueueInputKeys)
        && typeof input.content_id === "string"
        && /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(input.content_id)
        && positiveInteger(input.expected_asset_version) !== undefined
        && typeof input.target_kind === "string"
        && reviewTargetKinds.has(targetKind)
        && typeof input.target_digest === "string"
        && sha256ReferencePattern.test(input.target_digest)
        && positiveInteger(input.expected_head_version) !== undefined
        && boundedOpaque(input.expected_snapshot_id)
        && typeof input.expected_snapshot_digest === "string"
        && sha256ReferencePattern.test(input.expected_snapshot_digest)
        && typeof input.expected_head_value_digest === "string"
        && sha256ReferencePattern.test(input.expected_head_value_digest)
        && typeof input.original_value_digest === "string"
        && sha256ReferencePattern.test(input.original_value_digest)
        && exactRequiredText(input.reason, 2_000);
} } catch(e) {}
try { function loadReviewEnqueueAttempts(identityScope) {
    if (typeof sessionStorage === "undefined")
        return {};
    const storageKey = reviewEnqueueStorageKey(identityScope);
    try {
        const raw = sessionStorage.getItem(storageKey);
        if (!raw)
            return {};
        const parsed = parseStrictJson(raw);
        if (!Array.isArray(parsed) || parsed.length > maximumStoredReviewEnqueueAttempts) {
            throw new Error("HUMAN_REVIEW_ENQUEUE_RECOVERY_CORRUPT");
        }
        const attempts = {};
        for (const value of parsed) {
            if (!structurallyValidReviewEnqueueAttempt(value)
                || value.identity_scope !== identityScope
                || attempts[value.request_digest]) {
                throw new Error("HUMAN_REVIEW_ENQUEUE_RECOVERY_CORRUPT");
            }
            attempts[value.request_digest] = value;
        }
        const normalized = canonicalStrictJson(Object.values(attempts).sort((left, right) => left.request_digest.localeCompare(right.request_digest)));
        if (normalized !== raw) {
            try {
                sessionStorage.setItem(storageKey, normalized);
            }
            catch {
                // Keep the valid raw receipt and in-memory attempt; UNKNOWN never
                // becomes retryable merely because normalization could not persist.
            }
        }
        return attempts;
    }
    catch (error) {
        // A malformed or legacy receipt may still represent an UNKNOWN side
        // effect. Never erase it or silently turn it into a fresh retry.
        throw error instanceof Error
            ? error
            : new Error("HUMAN_REVIEW_ENQUEUE_RECOVERY_CORRUPT");
    }
} } catch(e) {}
try { function persistReviewEnqueueAttempts(identityScope, attempts) {
    const values = Object.values(attempts);
    if (typeof sessionStorage === "undefined"
        || values.length > maximumStoredReviewEnqueueAttempts
        || values.some((attempt) => (!structurallyValidReviewEnqueueAttempt(attempt)
            || attempt.identity_scope !== identityScope)))
        return false;
    values.sort((left, right) => left.request_digest.localeCompare(right.request_digest));
    try {
        sessionStorage.setItem(reviewEnqueueStorageKey(identityScope), canonicalStrictJson(values));
        return true;
    }
    catch {
        return false;
    }
} } catch(e) {}
try { async function reviewEnqueueRequestDigest(input) {
    return `sha256:${await sha256(new TextEncoder().encode(canonicalStrictJson(input)).buffer)}`;
} } catch(e) {}
try { async function reviewProjectScopeDigest(identityScope, projectId) {
    return `sha256:${await sha256(new TextEncoder().encode(canonicalStrictJson({
        schema_version: "multimodal-review-project-scope-v1",
        identity_scope: identityScope,
        project_id: projectId,
    })).buffer)}`;
} } catch(e) {}
try { async function validatedReviewEnqueuePreparation(value, attempt, expectedStates) {
    if (!value || typeof value !== "object" || Array.isArray(value)) {
        throw new Error("HUMAN_REVIEW_ENQUEUE_PREPARATION_INVALID");
    }
    const preparation = value;
    const state = preparation.state;
    const input = preparation.enqueue_input;
    if (!exactObjectFields(preparation, reviewEnqueuePreparationFields)
        || preparation.schema_version !== "human-review-enqueue-preparation-v1"
        || preparation.recovery_handle !== attempt.recovery_handle
        || preparation.request_digest !== attempt.request_digest
        || typeof state !== "string"
        || !expectedStates.has(state)
        || typeof preparation.safe_to_clear !== "boolean"
        || !exactTimestamp(preparation.expires_at)
        || !exactTimestamp(preparation.prepared_at)
        || Date.parse(preparation.expires_at) <= Date.parse(preparation.prepared_at)
        || !structurallyValidReviewSourceEnqueueInput(input)
        || await reviewEnqueueRequestDigest(input) !== attempt.request_digest)
        throw new Error("HUMAN_REVIEW_ENQUEUE_PREPARATION_INVALID");
    if (state === "PREPARED" && (preparation.safe_to_clear !== false
        || preparation.executed_at !== null
        || preparation.task_id !== null))
        throw new Error("HUMAN_REVIEW_ENQUEUE_PREPARATION_INVALID");
    if (state === "EXECUTED" && (preparation.safe_to_clear !== true
        || !exactTimestamp(preparation.executed_at)
        || !boundedOpaque(preparation.task_id)
        || Date.parse(preparation.executed_at) < Date.parse(preparation.prepared_at)))
        throw new Error("HUMAN_REVIEW_ENQUEUE_PREPARATION_INVALID");
    if (state === "EXPIRED" && (preparation.safe_to_clear !== true
        || preparation.executed_at !== null
        || preparation.task_id !== null))
        throw new Error("HUMAN_REVIEW_ENQUEUE_PREPARATION_INVALID");
    return { preparation, input };
} } catch(e) {}
try { function exactReviewEnqueuePreparationAbsence(value, attempt) {
    if (!value || typeof value !== "object" || Array.isArray(value))
        return false;
    const preparation = value;
    return exactObjectFields(preparation, reviewEnqueuePreparationAbsenceFields)
        && preparation.schema_version === "human-review-enqueue-preparation-absence-v1"
        && preparation.recovery_handle === attempt.recovery_handle
        && preparation.state === "ABSENT"
        && preparation.safe_to_clear === true;
} } catch(e) {}
try { const jobProgressResultByState = Object.freeze({
    QUEUED: "NOT_RUN",
    RUNNING: "NOT_RUN",
    COMPLETED: "PASSED",
    PARTIAL: "PARTIAL",
    NEEDS_REVIEW: "NEEDS_REVIEW",
    BLOCKED: "BLOCKED",
    FAILED: "FAILED",
    CANCELLED: "BLOCKED",
}); } catch(e) {}
try { async function validatedJobProgressEvent(source, jobId, lastEventId) {
    const value = parseStrictJson(source, { maximumDepth: 4, maximumNodes: 32 });
    if (!value || typeof value !== "object" || Array.isArray(value)) {
        throw new Error("MULTIMODAL_PROGRESS_EVENT_INVALID");
    }
    const event = value;
    const fields = new Set([
        "schema_version", "kind", "resource_id", "sequence_number", "event_type",
        "state", "result_status", "attempt", "max_attempts", "occurred_at",
        "content_digest", "cursor",
    ]);
    const state = event.state;
    if (!exactObjectFields(event, fields)
        || event.schema_version !== "1.0.0"
        || event.kind !== "JOB_PROGRESS"
        || event.resource_id !== jobId
        || typeof event.sequence_number !== "number"
        || !Number.isSafeInteger(event.sequence_number)
        || event.sequence_number < 1
        || event.event_type !== "processing.job.snapshot"
        || typeof state !== "string"
        || !Object.hasOwn(jobProgressResultByState, state)
        || event.result_status !== jobProgressResultByState[state]
        || typeof event.attempt !== "number"
        || !Number.isSafeInteger(event.attempt)
        || typeof event.max_attempts !== "number"
        || !Number.isSafeInteger(event.max_attempts)
        || event.attempt < 0
        || event.max_attempts < 1
        || event.attempt > event.max_attempts
        || !exactTimestamp(event.occurred_at)
        || typeof event.content_digest !== "string"
        || !sha256ReferencePattern.test(event.content_digest)
        || typeof event.cursor !== "string"
        || event.cursor !== lastEventId)
        throw new Error("MULTIMODAL_PROGRESS_EVENT_INVALID");
    const unsigned = { ...event };
    delete unsigned.content_digest;
    delete unsigned.cursor;
    const digest = await sha256(new TextEncoder().encode(canonicalStrictJson(unsigned)).buffer);
    if (event.content_digest !== `sha256:${digest}`
        || event.cursor !== `p1-${event.sequence_number}-${digest}`)
        throw new Error("MULTIMODAL_PROGRESS_EVENT_DIGEST_INVALID");
    return event;
} } catch(e) {}
try { function structurallyValidReviewClaim(value) {
    if (!value || typeof value !== "object" || Array.isArray(value))
        return false;
    const claim = value;
    if (Object.keys(claim).some((key) => !reviewClaimKeys.has(key)))
        return false;
    const fence = claim.fence;
    const expiresAt = claim.expires_at;
    if (claim.schema_version !== 2
        || typeof claim.identity_scope !== "string"
        || !/^sha256:[0-9a-f]{64}$/.test(claim.identity_scope)
        || typeof claim.project_id !== "string"
        || !safeProject(claim.project_id)
        || typeof claim.task_id !== "string"
        || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(claim.task_id)
        || !boundedOpaque(claim.token)
        || !boundedOpaque(claim.idempotency_key)
        || new TextEncoder().encode(claim.token).byteLength < 8
        || new TextEncoder().encode(claim.token).byteLength > 200
        || new TextEncoder().encode(claim.idempotency_key).byteLength < 8
        || new TextEncoder().encode(claim.idempotency_key).byteLength > 200
        || typeof claim.expected_version !== "number"
        || !Number.isSafeInteger(claim.expected_version)
        || claim.expected_version < 1
        || typeof claim.created_at !== "number"
        || !Number.isSafeInteger(claim.created_at)
        || claim.created_at < 0
        || claim.created_at > Date.now() + 60_000
        || ((fence === undefined) !== (expiresAt === undefined))
        || (fence !== undefined && (typeof fence !== "number"
            || !Number.isSafeInteger(fence)
            || fence < 1
            || typeof expiresAt !== "string"
            || !Number.isFinite(Date.parse(expiresAt)))))
        return false;
    return true;
} } catch(e) {}
try { function validReviewClaim(value, identityScope, now = Date.now()) {
    if (!structurallyValidReviewClaim(value) || value.identity_scope !== identityScope)
        return false;
    if (value.fence === undefined) {
        return now - value.created_at <= pendingReviewClaimRecoveryMs;
    }
    return Date.parse(value.expires_at) > now;
} } catch(e) {}
try { function loadReviewClaims(identityScope) {
    if (typeof sessionStorage === "undefined")
        return {};
    try {
        const storageKey = reviewClaimStorageKey(identityScope);
        const raw = sessionStorage.getItem(storageKey);
        if (!raw)
            return {};
        const parsed = parseStrictJson(raw);
        if (!Array.isArray(parsed) || parsed.length > maximumStoredReviewClaims) {
            sessionStorage.removeItem(storageKey);
            return {};
        }
        const claims = {};
        for (const value of parsed) {
            if (!structurallyValidReviewClaim(value) || claims[value.task_id]) {
                sessionStorage.removeItem(storageKey);
                return {};
            }
            if (validReviewClaim(value, identityScope))
                claims[value.task_id] = value;
        }
        const retained = Object.values(claims).sort((left, right) => left.task_id.localeCompare(right.task_id));
        const normalized = canonicalStrictJson(retained);
        if (normalized !== raw) {
            try {
                sessionStorage.setItem(storageKey, normalized);
            }
            catch {
                // Keep recoverable in-memory receipts; a storage failure must not erase them.
            }
        }
        return claims;
    }
    catch {
        try {
            sessionStorage.removeItem(reviewClaimStorageKey(identityScope));
        }
        catch {
            // The next server operation still validates actor, task version, token and fence.
        }
        return {};
    }
} } catch(e) {}
try { function persistReviewClaims(claims, identityScope) {
    if (typeof sessionStorage === "undefined")
        return false;
    const values = Object.values(claims);
    if (values.length > maximumStoredReviewClaims
        || values.some((claim) => !validReviewClaim(claim, identityScope)))
        return false;
    values.sort((left, right) => left.task_id.localeCompare(right.task_id));
    try {
        sessionStorage.setItem(reviewClaimStorageKey(identityScope), canonicalStrictJson(values));
        return true;
    }
    catch {
        return false;
    }
} } catch(e) {}
try { function validRecoveryRecord(value) {
    if (!value || typeof value !== "object" || Array.isArray(value))
        return false;
    const record = value;
    if (Object.keys(record).some((key) => !recoveryRecordKeys.has(key)))
        return false;
    if (record.schemaVersion !== 2
        || typeof record.identityScope !== "string"
        || !/^sha256:[0-9a-f]{64}$/.test(record.identityScope)
        || typeof record.fileFingerprint !== "string"
        || !/^[0-9a-f]{64}$/.test(record.fileFingerprint)
        || typeof record.expectedSize !== "number"
        || !Number.isSafeInteger(record.expectedSize)
        || record.expectedSize <= 0
        || record.expectedSize > maximumProcessableAssetBytes
        || typeof record.lastModified !== "number"
        || !Number.isSafeInteger(record.lastModified)
        || record.lastModified < 0
        || record.partSize !== chunkBytes
        || !boundedOpaque(record.attemptKey)
        || typeof record.projectId !== "string"
        || !safeProject(record.projectId)
        || !boundedOpaque(record.engineProjectId)
        || !boundedOpaque(record.sessionAttemptKey)
        || typeof record.confirmedPartCount !== "number"
        || !Number.isSafeInteger(record.confirmedPartCount)
        || record.confirmedPartCount < 0
        || record.confirmedPartCount > Math.ceil(record.expectedSize / chunkBytes)
        || typeof record.processingAttempt !== "number"
        || !Number.isSafeInteger(record.processingAttempt)
        || record.processingAttempt < 0
        || record.processingAttempt > 10_000
        || !["PRIMARY", "REFERENCE", "IGNORE"].includes(String(record.role))
        || typeof record.modelReadAllowed !== "boolean"
        || record.role === "IGNORE" && record.modelReadAllowed
        || typeof record.updatedAt !== "number"
        || !Number.isSafeInteger(record.updatedAt)
        || record.updatedAt < 0)
        return false;
    for (const key of ["sessionId", "uploadSessionId", "assetId"]) {
        if (record[key] !== undefined && !boundedOpaque(record[key]))
            return false;
    }
    if (record.contentSha256 !== undefined && (typeof record.contentSha256 !== "string" || !/^[0-9a-f]{64}$/.test(record.contentSha256)))
        return false;
    if (record.assetVersion !== undefined && (typeof record.assetVersion !== "number"
        || !Number.isSafeInteger(record.assetVersion)
        || record.assetVersion <= 0))
        return false;
    if (record.uploadSessionId && (!record.sessionId || !record.contentSha256))
        return false;
    if (record.confirmedPartCount > 0 && !record.uploadSessionId)
        return false;
    if (record.assetId && (!record.uploadSessionId || !record.contentSha256))
        return false;
    return true;
} } catch(e) {}
try { function recoveryStorageKey(record) {
    return JSON.stringify([
        record.identityScope,
        record.projectId,
        record.engineProjectId,
        record.fileFingerprint,
    ]);
} } catch(e) {}
try { function openRecoveryDatabase() {
    if (typeof indexedDB === "undefined")
        return Promise.reject(new Error("RECOVERY_STORE_UNAVAILABLE"));
    return new Promise((resolve, reject) => {
        const request = indexedDB.open(recoveryDatabaseName, 3);
        request.onupgradeneeded = () => {
            // v1/v2 records could not prove browser identity scope. They contain
            // recovery credentials and therefore cannot be adopted by the active
            // account. Discard them on upgrade; v3 keeps each identity independent.
            if (request.result.objectStoreNames.contains(recoveryStoreName)) {
                request.result.deleteObjectStore(recoveryStoreName);
            }
            request.result.createObjectStore(recoveryStoreName, {
                keyPath: ["identityScope", "projectId", "engineProjectId", "fileFingerprint"],
            });
        };
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(new Error("RECOVERY_STORE_UNAVAILABLE"));
        request.onblocked = () => reject(new Error("RECOVERY_STORE_BLOCKED"));
    });
} } catch(e) {}
try { async function readRecoveryValues() {
    const database = await openRecoveryDatabase();
    return new Promise((resolve, reject) => {
        const transaction = database.transaction(recoveryStoreName, "readonly");
        const request = transaction.objectStore(recoveryStoreName).getAll();
        let values = [];
        request.onsuccess = () => { values = request.result; };
        request.onerror = () => reject(new Error("RECOVERY_STORE_READ_FAILED"));
        transaction.oncomplete = () => { database.close(); resolve(values); };
        transaction.onerror = () => { database.close(); reject(new Error("RECOVERY_STORE_READ_FAILED")); };
        transaction.onabort = () => { database.close(); reject(new Error("RECOVERY_STORE_READ_FAILED")); };
    });
} } catch(e) {}
try { async function replaceRecoveryValues(records) {
    const database = await openRecoveryDatabase();
    await new Promise((resolve, reject) => {
        const transaction = database.transaction(recoveryStoreName, "readwrite");
        const store = transaction.objectStore(recoveryStoreName);
        store.clear();
        for (const record of records)
            store.put(record);
        transaction.oncomplete = () => { database.close(); resolve(); };
        transaction.onerror = () => { database.close(); reject(new Error("RECOVERY_STORE_WRITE_FAILED")); };
        transaction.onabort = () => { database.close(); reject(new Error("RECOVERY_STORE_WRITE_FAILED")); };
    });
} } catch(e) {}
try { async function putRecoveryValue(record) {
    const database = await openRecoveryDatabase();
    await new Promise((resolve, reject) => {
        const transaction = database.transaction(recoveryStoreName, "readwrite");
        transaction.objectStore(recoveryStoreName).put(record);
        transaction.oncomplete = () => { database.close(); resolve(); };
        transaction.onerror = () => { database.close(); reject(new Error("RECOVERY_STORE_WRITE_FAILED")); };
        transaction.onabort = () => { database.close(); reject(new Error("RECOVERY_STORE_WRITE_FAILED")); };
    });
} } catch(e) {}
try { async function deleteRecoveryValue(record) {
    const database = await openRecoveryDatabase();
    await new Promise((resolve, reject) => {
        const transaction = database.transaction(recoveryStoreName, "readwrite");
        transaction.objectStore(recoveryStoreName).delete([
            record.identityScope,
            record.projectId,
            record.engineProjectId,
            record.fileFingerprint,
        ]);
        transaction.oncomplete = () => { database.close(); resolve(); };
        transaction.onerror = () => { database.close(); reject(new Error("RECOVERY_STORE_WRITE_FAILED")); };
        transaction.onabort = () => { database.close(); reject(new Error("RECOVERY_STORE_WRITE_FAILED")); };
    });
} } catch(e) {}
try { function nestedRecord(response) {
    for (const candidate of [response.output, response.outputs, response.data, response.result]) {
        if (candidate && typeof candidate === "object" && !Array.isArray(candidate))
            return candidate;
    }
    return response;
} } catch(e) {}
try { function projectPackagePage(response) {
    const output = nestedRecord(response);
    const items = output.items;
    const packageVersion = output.package_version;
    const nextCursor = output.next_cursor;
    const total = output.total;
    const collectionDigest = output.collection_digest;
    if (!Number.isSafeInteger(packageVersion) || Number(packageVersion) < 1
        || !Number.isSafeInteger(total) || Number(total) < 0
        || !Array.isArray(items) || items.length > 200
        || !(nextCursor === null || typeof nextCursor === "string")
        || typeof collectionDigest !== "string" || !/^[0-9a-f]{64}$/.test(collectionDigest))
        throw new Error("PROJECT_PACKAGE_PAGE_INVALID");
    const normalized = items.map((item) => {
        if (!item || typeof item !== "object" || Array.isArray(item)) {
            throw new Error("PROJECT_PACKAGE_PAGE_ENTRY_INVALID");
        }
        const entry = item;
        if (typeof entry.path !== "string" || typeof entry.kind !== "string"
            || !["PRIMARY", "REFERENCE", "IGNORE"].includes(String(entry.role))
            || typeof entry.model_read_allowed !== "boolean"
            || typeof entry.security_state !== "string"
            || !Number.isSafeInteger(entry.override_version))
            throw new Error("PROJECT_PACKAGE_PAGE_ENTRY_INVALID");
        return entry;
    });
    return {
        package_version: Number(packageVersion),
        items: normalized,
        next_cursor: nextCursor,
        total: Number(total),
        collection_digest: collectionDigest,
    };
} } catch(e) {}
try { function processingEstimate(response, inputDigest) {
    const output = nestedRecord(response);
    const ledger = output.ledger;
    const p50 = output.remaining_seconds_p50;
    const p95 = output.remaining_seconds_p95;
    const estimatedCost = output.estimated_cost;
    const currency = output.currency;
    const calibrationVersion = output.calibration_version;
    const estimateDigest = output.estimate_digest;
    const status = String(response.status ?? response.state ?? "").toUpperCase();
    if (!["SUCCEEDED", "PARTIAL"].includes(status)
        || typeof p50 !== "number" || !Number.isFinite(p50) || p50 < 0
        || typeof p95 !== "number" || !Number.isFinite(p95) || p95 < p50
        || typeof estimatedCost !== "string" || !/^(?:0|[1-9][0-9]*)(?:\.[0-9]{1,18})?$/.test(estimatedCost)
        || typeof currency !== "string" || !/^[A-Z]{3}$/.test(currency)
        || typeof calibrationVersion !== "string" || !boundedOpaque(calibrationVersion)
        || typeof estimateDigest !== "string" || !/^sha256:[0-9a-f]{64}$/.test(estimateDigest)
        || !ledger || typeof ledger !== "object" || Array.isArray(ledger))
        throw new Error("PROCESSING_ESTIMATE_RESPONSE_INVALID");
    const actualsState = ledger.actuals_state;
    if (ledger.schema_version !== "multimodal-cost-ledger-v1"
        || typeof actualsState !== "string"
        || !["NOT_RUN", "PENDING", "RECONCILED", "UNKNOWN", "BLOCKED"].includes(actualsState))
        throw new Error("PROCESSING_ESTIMATE_LEDGER_INVALID");
    return {
        inputDigest,
        status: status === "SUCCEEDED" ? "READY" : "PARTIAL",
        code: responseString(response, "code") ?? "PROCESSING_COST_ETA_ESTIMATED",
        remainingSecondsP50: p50,
        remainingSecondsP95: p95,
        estimatedCost,
        currency,
        actualsState,
        calibrationVersion,
        estimateDigest,
    };
} } catch(e) {}
try { function estimateFileType(file) {
    const extension = extensionOf(file);
    if (["png", "jpg", "jpeg", "webp", "heic", "tiff", "bmp", "svg"].includes(extension)) {
        return "image/*";
    }
    if (["mp3", "wav", "m4a", "aac", "flac", "ogg", "opus"].includes(extension)) {
        return "audio/*";
    }
    if (extension === "pdf")
        return "application/pdf";
    if (["doc", "docx"].includes(extension))
        return "application/word";
    if (["zip", "tar", "tar.gz", "gz", "tgz"].includes(extension))
        return "application/archive";
    return "text/plain";
} } catch(e) {}
try { function formatEstimateDuration(seconds) {
    if (seconds < 60)
        return `${Math.ceil(seconds)} 秒`;
    if (seconds < 3_600)
        return `${Math.ceil(seconds / 60)} 分钟`;
    return `${(seconds / 3_600).toFixed(1)} 小时`;
} } catch(e) {}
try { function responseString(response, ...keys) {
    const sources = [response, nestedRecord(response)];
    for (const source of sources) {
        for (const key of keys) {
            const value = source[key];
            if (typeof value === "string" && value)
                return value;
        }
    }
    return undefined;
} } catch(e) {}
try { function outputRecord(response, key) {
    const value = nestedRecord(response)[key];
    return value && typeof value === "object" && !Array.isArray(value)
        ? value
        : undefined;
} } catch(e) {}
try { function exactReviewOutput(response, keys) {
    const output = nestedRecord(response);
    if (Object.keys(output).length !== keys.length
        || Object.keys(output).some((key) => !keys.includes(key))) {
        throw new Error("HUMAN_REVIEW_OUTPUT_FIELDS_INVALID");
    }
    return output;
} } catch(e) {}
try { const reviewPropagationChannels = new Set([
    "content-index", "requirements", "project-memory", "downstream",
]); } catch(e) {}
try { function validReviewPropagations(value, taskId, options) {
    if (!Array.isArray(value))
        return false;
    const ids = new Set();
    const channels = new Set();
    const payloadDigests = new Set();
    const effectiveDigests = new Set();
    for (const item of value) {
        if (!item || typeof item !== "object" || Array.isArray(item))
            return false;
        const propagation = item;
        if (!exactObjectFields(propagation, reviewPropagationSummaryFields))
            return false;
        const expiresAt = propagation.claim_expires_at;
        const dispatchStartedAt = propagation.dispatch_started_at;
        const failureCode = propagation.failure_code;
        const state = propagation.state;
        const claimFence = propagation.claim_fence;
        if (typeof propagation.propagation_id !== "string"
            || !boundedOpaque(propagation.propagation_id)
            || ids.has(propagation.propagation_id)
            || propagation.task_id !== taskId
            || typeof propagation.channel !== "string"
            || !reviewPropagationChannels.has(propagation.channel)
            || options.exactBatch && channels.has(propagation.channel)
            || !["APPLY", "REVERT"].includes(String(propagation.direction))
            || options.direction !== undefined && propagation.direction !== options.direction
            || options.decisionId !== undefined && propagation.decision_id !== options.decisionId
            || options.correctionVersion !== undefined
                && propagation.correction_version !== options.correctionVersion
            || !boundedOpaque(propagation.decision_id)
            || positiveInteger(propagation.correction_version) === undefined
            || typeof propagation.payload_digest !== "string"
            || !sha256ReferencePattern.test(propagation.payload_digest)
            || typeof propagation.effective_value_digest !== "string"
            || !sha256ReferencePattern.test(propagation.effective_value_digest)
            || typeof state !== "string"
            || !["PENDING", "CLAIMED", "SUCCEEDED", "FAILED", "UNKNOWN"].includes(state)
            || typeof claimFence !== "number"
            || !Number.isSafeInteger(claimFence)
            || claimFence < 0
            || !(expiresAt === null || exactTimestamp(expiresAt))
            || !(dispatchStartedAt === null || exactTimestamp(dispatchStartedAt))
            || !(failureCode === null || boundedOpaque(failureCode))
            || typeof propagation.reconciliation_required !== "boolean"
            || positiveInteger(propagation.version) === undefined
            || !exactTimestamp(propagation.updated_at)
            || options.initial === true && (state !== "PENDING" || claimFence !== 0 || propagation.version !== 1)
            || state === "PENDING" && (expiresAt !== null || dispatchStartedAt !== null || failureCode !== null
                || propagation.reconciliation_required !== false)
            || state === "CLAIMED" && (claimFence < 1 || !exactTimestamp(expiresAt) || failureCode !== null
                || propagation.reconciliation_required !== false)
            || state === "SUCCEEDED" && (expiresAt !== null || !exactTimestamp(dispatchStartedAt) || failureCode !== null
                || propagation.reconciliation_required !== false)
            || state === "FAILED" && (expiresAt !== null || !exactTimestamp(dispatchStartedAt) || !boundedOpaque(failureCode)
                || propagation.reconciliation_required !== false)
            || state === "UNKNOWN" && (expiresAt !== null || !exactTimestamp(dispatchStartedAt) || !boundedOpaque(failureCode)
                || propagation.reconciliation_required !== true))
            return false;
        ids.add(propagation.propagation_id);
        channels.add(propagation.channel);
        payloadDigests.add(propagation.payload_digest);
        effectiveDigests.add(propagation.effective_value_digest);
    }
    return !options.exactBatch || (value.length === reviewPropagationChannels.size
        && channels.size === reviewPropagationChannels.size
        && payloadDigests.size === reviewPropagationChannels.size
        && effectiveDigests.size === 1);
} } catch(e) {}
try { function validHistoricalPropagationBatches(value, taskId) {
    if (!validReviewPropagations(value, taskId, { exactBatch: false }))
        return false;
    const groups = new Map();
    for (const propagation of value) {
        const decisionId = propagation.decision_id;
        groups.set(decisionId, [...(groups.get(decisionId) ?? []), propagation]);
    }
    for (const group of groups.values()) {
        const channels = new Set(group.map((item) => item.channel));
        const correctionVersions = new Set(group.map((item) => item.correction_version));
        const directions = new Set(group.map((item) => item.direction));
        const payloadDigests = new Set(group.map((item) => item.payload_digest));
        const effectiveDigests = new Set(group.map((item) => item.effective_value_digest));
        if (group.length !== reviewPropagationChannels.size
            || channels.size !== reviewPropagationChannels.size
            || correctionVersions.size !== 1
            || directions.size !== 1
            || payloadDigests.size !== reviewPropagationChannels.size
            || effectiveDigests.size !== 1)
            return false;
    }
    return true;
} } catch(e) {}
try { function positiveInteger(value) {
    return typeof value === "number" && Number.isSafeInteger(value) && value > 0 ? value : undefined;
} } catch(e) {}
try { const reviewTargetKinds = new Set([
    "TEXT", "SPEAKER", "TIME_RANGE", "BBOX", "TABLE", "REQUIREMENT", "CONFLICT",
]); } catch(e) {}
try { const sha256ReferencePattern = /^sha256:[0-9a-f]{64}$/; } catch(e) {}
try { function exactReviewTarget(kind, value) {
    if (!value || typeof value !== "object" || Array.isArray(value))
        return false;
    const target = value;
    const exactKeys = (...keys) => (Object.keys(target).length === keys.length && keys.every((key) => Object.hasOwn(target, key)));
    const resourceId = (candidate) => (typeof candidate === "string" && /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(candidate));
    const safeNonNegativeInteger = (candidate) => (typeof candidate === "number" && Number.isSafeInteger(candidate) && candidate >= 0);
    if (kind === "TEXT") {
        return exactKeys("path") && typeof target.path === "string"
            && target.path.length > 0 && target.path === target.path.trim()
            && !/[\u0000-\u001f\u007f]/.test(target.path)
            && new TextEncoder().encode(target.path).byteLength <= 1_024;
    }
    if (kind === "SPEAKER")
        return exactKeys("segment_id") && resourceId(target.segment_id);
    if (kind === "TIME_RANGE") {
        return exactKeys("start_ms", "end_ms")
            && safeNonNegativeInteger(target.start_ms)
            && safeNonNegativeInteger(target.end_ms)
            && Number(target.end_ms) >= Number(target.start_ms);
    }
    if (kind === "BBOX") {
        return exactKeys("page", "x", "y", "width", "height")
            && typeof target.page === "number" && Number.isSafeInteger(target.page) && target.page >= 1
            && [target.x, target.y, target.width, target.height].every((candidate) => (typeof candidate === "number" && Number.isFinite(candidate) && candidate >= 0))
            && Number(target.width) > 0 && Number(target.height) > 0;
    }
    if (kind === "TABLE") {
        return exactKeys("table_id", "row", "column") && resourceId(target.table_id)
            && safeNonNegativeInteger(target.row) && safeNonNegativeInteger(target.column);
    }
    if (kind === "REQUIREMENT") {
        return exactKeys("requirement_id") && resourceId(target.requirement_id);
    }
    return exactKeys("conflict_id") && resourceId(target.conflict_id);
} } catch(e) {}
try { function exactTimestamp(value) {
    if (typeof value !== "string" || !boundedOpaque(value))
        return false;
    const matched = /^(\d{4})-(\d{2})-(\d{2})T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d+)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$/.exec(value);
    if (!matched || !Number.isFinite(Date.parse(value)))
        return false;
    const year = Number(matched[1]);
    const month = Number(matched[2]);
    const day = Number(matched[3]);
    if (year < 1 || month < 1 || month > 12)
        return false;
    const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
    const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    return day >= 1 && day <= days[month - 1];
} } catch(e) {}
try { function exactRequiredText(value, maximumBytes) {
    return typeof value === "string"
        && value.length > 0
        && value === value.trim()
        && new TextEncoder().encode(value).byteLength <= maximumBytes;
} } catch(e) {}
try { function exactObjectFields(value, fields) {
    return Object.keys(value).length === fields.size
        && Object.keys(value).every((key) => fields.has(key));
} } catch(e) {}
try { function exactReviewSourceRef(value, task) {
    if (!value || typeof value !== "object" || Array.isArray(value))
        return false;
    const source = value;
    if (!exactObjectFields(source, reviewSourceRefFields))
        return false;
    const digestFields = [
        "content_digest", "asset_sha256", "target_digest", "snapshot_digest",
        "head_value_digest", "source_digest", "provenance_digest",
        "original_value_client_digest",
    ];
    return source.schema_version === "human-review-source-ref-v2"
        && source.content_id === task.assetId
        && positiveInteger(source.content_version) !== undefined
        && source.target_kind === task.targetKind
        && typeof source.snapshot_id === "string"
        && boundedOpaque(source.snapshot_id)
        && positiveInteger(source.head_version) !== undefined
        && source.head_value_digest === task.sourceDigest
        && source.original_value_digest_contract === "sha256:rfc8785-ijson-safeint-v1"
        && digestFields.every((field) => (typeof source[field] === "string" && sha256ReferencePattern.test(source[field])));
} } catch(e) {}
try { function reviewSource(value) {
    if (!value || typeof value !== "object" || Array.isArray(value))
        return undefined;
    const candidate = value;
    const detail = candidate.schema_version === "human-review-source-detail-v1";
    if (!exactObjectFields(candidate, detail ? reviewSourceDetailFields : reviewSourceSummaryFields)) {
        return undefined;
    }
    if (!candidate.source_ref || typeof candidate.source_ref !== "object" || Array.isArray(candidate.source_ref)) {
        return undefined;
    }
    const sourceRef = candidate.source_ref;
    const targetKind = candidate.target_kind;
    const contentVersion = positiveInteger(candidate.content_version);
    const headVersion = positiveInteger(candidate.head_version);
    const headCorrectionVersion = typeof candidate.head_correction_version === "number"
        && Number.isSafeInteger(candidate.head_correction_version)
        && candidate.head_correction_version >= 0
        ? candidate.head_correction_version
        : undefined;
    const confidence = candidate.confidence;
    const headDirection = candidate.head_direction;
    if (typeof candidate.content_id !== "string"
        || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(candidate.content_id)
        || contentVersion === undefined
        || typeof candidate.target_kind !== "string"
        || !reviewTargetKinds.has(targetKind)
        || !exactReviewTarget(targetKind, candidate.target)
        || typeof candidate.target_digest !== "string"
        || !sha256ReferencePattern.test(candidate.target_digest)
        || typeof confidence !== "number"
        || !Number.isFinite(confidence)
        || confidence < 0
        || confidence > 1
        || headVersion === undefined
        || !["SNAPSHOT", "APPLY", "REVERT"].includes(String(headDirection))
        || headCorrectionVersion === undefined
        || headDirection === "SNAPSHOT" && headCorrectionVersion !== 0
        || headDirection === "APPLY" && headCorrectionVersion < 1
        || typeof candidate.original_value_client_digest !== "string"
        || !sha256ReferencePattern.test(candidate.original_value_client_digest)
        || candidate.original_value_digest_contract !== "sha256:rfc8785-ijson-safeint-v1"
        || !exactReviewSourceRef(sourceRef, {
            assetId: candidate.content_id,
            targetKind,
            sourceDigest: String(sourceRef.head_value_digest),
        })
        || sourceRef.content_version !== contentVersion
        || sourceRef.target_digest !== candidate.target_digest
        || sourceRef.head_version !== headVersion
        || sourceRef.original_value_client_digest !== candidate.original_value_client_digest)
        return undefined;
    return {
        schema_version: detail
            ? "human-review-source-detail-v1"
            : "human-review-source-summary-v1",
        content_id: candidate.content_id,
        content_version: contentVersion,
        target_kind: targetKind,
        target: candidate.target,
        target_digest: candidate.target_digest,
        confidence,
        head_version: headVersion,
        head_direction: headDirection,
        head_correction_version: headCorrectionVersion,
        original_value_client_digest: candidate.original_value_client_digest,
        original_value_digest_contract: "sha256:rfc8785-ijson-safeint-v1",
        source_ref: sourceRef,
        ...(detail ? { original_value: candidate.original_value } : {}),
        detail_loaded: detail,
    };
} } catch(e) {}
try { function reviewSourceKey(source) {
    return `${source.target_kind}:${source.target_digest}:${source.head_version}`;
} } catch(e) {}
try { async function validatedReviewSource(value, expected) {
    const source = reviewSource(value);
    if (!source
        || source.content_id !== expected.contentId
        || source.content_version !== expected.contentVersion)
        throw new Error("HUMAN_REVIEW_SOURCE_RESPONSE_INVALID");
    if (expected.priorSummary) {
        const summaryProjection = (candidate) => ({
            schema_version: "human-review-source-summary-v1",
            content_id: candidate.content_id,
            content_version: candidate.content_version,
            target_kind: candidate.target_kind,
            target: candidate.target,
            target_digest: candidate.target_digest,
            confidence: candidate.confidence,
            head_version: candidate.head_version,
            head_direction: candidate.head_direction,
            head_correction_version: candidate.head_correction_version,
            original_value_client_digest: candidate.original_value_client_digest,
            original_value_digest_contract: candidate.original_value_digest_contract,
            source_ref: candidate.source_ref,
        });
        if (!source.detail_loaded
            || canonicalStrictJson(summaryProjection(source))
                !== canonicalStrictJson(summaryProjection(expected.priorSummary)))
            throw new Error("HUMAN_REVIEW_SOURCE_DETAIL_BINDING_INVALID");
    }
    if (source.detail_loaded) {
        const observed = `sha256:${await sha256(new TextEncoder().encode(canonicalStrictJson(source.original_value)).buffer)}`;
        if (observed !== source.original_value_client_digest) {
            throw new Error("HUMAN_REVIEW_SOURCE_VALUE_DIGEST_INVALID");
        }
    }
    return source;
} } catch(e) {}
try { function reviewTask(value, expectedScope) {
    if (!value || typeof value !== "object" || Array.isArray(value))
        return undefined;
    const candidate = value;
    const summary = candidate.schema_version === "human-review-task-summary-v1";
    if (!exactObjectFields(candidate, summary ? reviewTaskSummaryFields : reviewTaskFullFields)) {
        return undefined;
    }
    if (!summary && (!expectedScope
        || candidate.tenant_id !== expectedScope.tenantId
        || candidate.project_id !== expectedScope.projectId
        || !boundedOpaque(candidate.created_by)))
        return undefined;
    const resourceId = (resource) => (typeof resource === "string" && /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(resource));
    const version = positiveInteger(candidate.version);
    const correctionVersion = typeof candidate.current_correction_version === "number"
        && Number.isSafeInteger(candidate.current_correction_version)
        && candidate.current_correction_version >= 0
        ? candidate.current_correction_version
        : undefined;
    const effectiveVersion = typeof candidate.effective_version === "number"
        && Number.isSafeInteger(candidate.effective_version)
        && candidate.effective_version >= 0
        ? candidate.effective_version
        : undefined;
    const claimFence = typeof candidate.claim_fence === "number"
        && Number.isSafeInteger(candidate.claim_fence)
        && candidate.claim_fence >= 0
        ? candidate.claim_fence
        : undefined;
    const targetKind = candidate.target_kind;
    const state = candidate.state;
    if (!resourceId(candidate.task_id)
        || !resourceId(candidate.asset_id)
        || typeof candidate.target_kind !== "string"
        || !reviewTargetKinds.has(targetKind)
        || typeof candidate.source_digest !== "string"
        || !sha256ReferencePattern.test(candidate.source_digest)
        || typeof candidate.confidence !== "number"
        || !Number.isFinite(candidate.confidence)
        || candidate.confidence < 0
        || candidate.confidence > 1
        || !exactRequiredText(candidate.reason, 2_000)
        || typeof candidate.state !== "string"
        || !reviewTaskStates.has(state)
        || version === undefined
        || correctionVersion === undefined
        || effectiveVersion === undefined
        || claimFence === undefined
        || !exactTimestamp(candidate.created_at)
        || !exactTimestamp(candidate.updated_at))
        return undefined;
    const correctionDigest = candidate.current_correction_digest;
    const effectiveDigest = candidate.effective_digest;
    if (!(correctionDigest === null || (typeof correctionDigest === "string" && sha256ReferencePattern.test(correctionDigest)))
        || (correctionVersion === 0) !== (correctionDigest === null)
        || !(effectiveDigest === null || (typeof effectiveDigest === "string" && sha256ReferencePattern.test(effectiveDigest)))
        || effectiveVersion > 0 && effectiveDigest === null)
        return undefined;
    const liveClaimState = state === "CLAIMED" || state === "EDITED";
    const claimActor = candidate.claim_actor_id;
    const claimExpiresAt = candidate.claim_expires_at;
    if (liveClaimState && (!boundedOpaque(claimActor) || !exactTimestamp(claimExpiresAt) || claimFence < 1)
        || !liveClaimState && (claimActor !== null || claimExpiresAt !== null))
        return undefined;
    const closedState = state === "APPROVED" || state === "REJECTED" || state === "REVERTED";
    if (closedState && !exactTimestamp(candidate.closed_at)
        || !closedState && candidate.closed_at !== null)
        return undefined;
    if (!summary && (!exactReviewTarget(targetKind, candidate.target)
        || !exactReviewSourceRef(candidate.source_ref, {
            assetId: candidate.asset_id,
            targetKind,
            sourceDigest: candidate.source_digest,
        })))
        return undefined;
    return {
        ...(!summary ? {
            tenant_id: candidate.tenant_id,
            project_id: candidate.project_id,
            created_by: candidate.created_by,
            target: candidate.target,
            original_value: candidate.original_value,
            source_ref: candidate.source_ref,
        } : {}),
        task_id: candidate.task_id,
        asset_id: candidate.asset_id,
        target_kind: targetKind,
        source_digest: candidate.source_digest,
        confidence: candidate.confidence,
        reason: candidate.reason,
        state,
        current_correction_version: correctionVersion,
        ...(typeof correctionDigest === "string" ? { current_correction_digest: correctionDigest } : {}),
        effective_version: effectiveVersion,
        ...(typeof effectiveDigest === "string" ? { effective_digest: effectiveDigest } : {}),
        ...(typeof claimActor === "string" ? { claim_actor_id: claimActor } : {}),
        claim_fence: claimFence,
        ...(typeof claimExpiresAt === "string" ? { claim_expires_at: claimExpiresAt } : {}),
        version,
        created_at: candidate.created_at,
        updated_at: candidate.updated_at,
        ...(typeof candidate.closed_at === "string" ? { closed_at: candidate.closed_at } : {}),
        detail_loaded: !summary,
    };
} } catch(e) {}
try { function exactCurrentReviewCorrection(value, task) {
    if (!value || typeof value !== "object" || Array.isArray(value))
        return false;
    const correction = value;
    return task.detail_loaded === true
        && task.current_correction_version > 0
        && typeof task.current_correction_digest === "string"
        && exactObjectFields(correction, reviewCorrectionFields)
        && boundedOpaque(correction.correction_id)
        && correction.tenant_id === task.tenant_id
        && correction.project_id === task.project_id
        && correction.task_id === task.task_id
        && correction.correction_version === task.current_correction_version
        && correction.parent_correction_version === task.current_correction_version - 1
        && correction.target_kind === task.target_kind
        && canonicalStrictJson(correction.target) === canonicalStrictJson(task.target)
        && typeof correction.source_digest === "string"
        && sha256ReferencePattern.test(correction.source_digest)
        && boundedOpaque(correction.actor_id)
        && exactRequiredText(correction.reason, 2_000)
        && exactTimestamp(correction.created_at)
        && correction.correction_digest === task.current_correction_digest;
} } catch(e) {}
try { function exactReviewCorrection(value, priorTask, nextTask, correctedValue, reason) {
    if (!exactCurrentReviewCorrection(value, nextTask))
        return false;
    const correction = value;
    const expectedSourceDigest = (priorTask.effective_version ?? 0) > 0
        ? priorTask.effective_digest
        : priorTask.source_digest;
    return correction.task_id === priorTask.task_id
        && correction.parent_correction_version === priorTask.current_correction_version
        && correction.correction_version === priorTask.current_correction_version + 1
        && correction.target_kind === priorTask.target_kind
        && canonicalStrictJson(correction.target) === canonicalStrictJson(priorTask.target)
        && ((priorTask.effective_version ?? 0) > 0
            || canonicalStrictJson(correction.original_value) === canonicalStrictJson(priorTask.original_value))
        && canonicalStrictJson(correction.corrected_value) === canonicalStrictJson(correctedValue)
        && typeof expectedSourceDigest === "string"
        && correction.source_digest === expectedSourceDigest
        && correction.actor_id === priorTask.claim_actor_id
        && correction.reason === reason
        && correction.correction_digest === nextTask.current_correction_digest;
} } catch(e) {}
try { function exactReviewDecision(value, priorTask, nextTask, operation, reason, currentCorrection, trustedActorId) {
    if (!value || typeof value !== "object" || Array.isArray(value))
        return false;
    const decision = value;
    const expectedDecision = operation.toUpperCase();
    const expectedCorrectionVersion = priorTask.current_correction_version > 0
        ? priorTask.current_correction_version
        : null;
    const expectedCorrectionDigest = priorTask.current_correction_digest ?? null;
    const expectedActor = operation === "approve" || operation === "reject"
        ? priorTask.claim_actor_id
        : trustedActorId;
    return exactObjectFields(decision, reviewDecisionFields)
        && boundedOpaque(decision.decision_id)
        && decision.tenant_id === nextTask.tenant_id
        && decision.project_id === nextTask.project_id
        && decision.task_id === priorTask.task_id
        && decision.decision_version === nextTask.version
        && nextTask.version === priorTask.version + 1
        && decision.decision === expectedDecision
        && decision.prior_state === priorTask.state
        && decision.next_state === nextTask.state
        && decision.correction_version === expectedCorrectionVersion
        && decision.correction_digest === expectedCorrectionDigest
        && (expectedCorrectionVersion === null
            ? currentCorrection === undefined && decision.source_digest === priorTask.source_digest
            : currentCorrection !== undefined
                && exactCurrentReviewCorrection(currentCorrection, priorTask)
                && decision.source_digest === currentCorrection.source_digest)
        && boundedOpaque(decision.actor_id)
        && (expectedActor === undefined || decision.actor_id === expectedActor)
        && decision.reason === reason
        && exactTimestamp(decision.created_at)
        && (!(operation === "approve" || operation === "revert")
            || expectedCorrectionVersion !== null && expectedCorrectionDigest !== null);
} } catch(e) {}
try { function exactReviewEffective(value, task, propagations) {
    if (!value || typeof value !== "object" || Array.isArray(value))
        return false;
    const effective = value;
    if (!exactObjectFields(effective, reviewEffectiveFields)
        || typeof effective.materialized !== "boolean"
        || effective.effective_version !== task.effective_version
        || effective.effective_value_digest !== (task.effective_digest ?? null)
        || !Array.isArray(effective.channels))
        return false;
    if (!effective.materialized) {
        return effective.state === "NOT_RUN"
            && effective.effective_value === null
            && effective.effective_value_digest === null
            && effective.channels.length === 0;
    }
    if (effective.state !== "CURRENT"
        || typeof effective.effective_value_digest !== "string"
        || !sha256ReferencePattern.test(effective.effective_value_digest)
        || effective.channels.length !== reviewPropagationChannels.size)
        return false;
    const channels = new Set();
    const decisionIds = new Set();
    const correctionVersions = new Set();
    const directions = new Set();
    for (const item of effective.channels) {
        if (!item || typeof item !== "object" || Array.isArray(item))
            return false;
        const channel = item;
        if (!exactObjectFields(channel, reviewEffectiveChannelFields)
            || typeof channel.channel !== "string"
            || !reviewPropagationChannels.has(channel.channel)
            || channels.has(channel.channel)
            || !boundedOpaque(channel.source_decision_id)
            || positiveInteger(channel.correction_version) === undefined
            || !["APPLY", "REVERT"].includes(String(channel.direction))
            || channel.effective_value_digest !== effective.effective_value_digest
            || positiveInteger(channel.version) === undefined
            || !exactTimestamp(channel.updated_at))
            return false;
        channels.add(channel.channel);
        decisionIds.add(channel.source_decision_id);
        correctionVersions.add(channel.correction_version);
        directions.add(channel.direction);
    }
    if (channels.size !== reviewPropagationChannels.size
        || decisionIds.size !== 1
        || correctionVersions.size !== 1
        || directions.size !== 1
        || !Array.isArray(propagations))
        return false;
    const [decisionId] = decisionIds;
    const [correctionVersion] = correctionVersions;
    const [direction] = directions;
    const sourceBatch = propagations.filter((item) => (item && typeof item === "object" && !Array.isArray(item)
        && item.decision_id === decisionId));
    const sourceChannels = new Set();
    for (const propagation of sourceBatch) {
        if (propagation.task_id !== task.task_id
            || propagation.correction_version !== correctionVersion
            || propagation.direction !== direction
            || propagation.effective_value_digest !== effective.effective_value_digest
            || propagation.state !== "SUCCEEDED"
            || typeof propagation.channel !== "string"
            || !reviewPropagationChannels.has(propagation.channel)
            || sourceChannels.has(propagation.channel))
            return false;
        sourceChannels.add(propagation.channel);
    }
    return sourceBatch.length === reviewPropagationChannels.size
        && sourceChannels.size === reviewPropagationChannels.size;
} } catch(e) {}
try { function reviewTaskDynamicState(task) {
    return {
        state: task.state,
        current_correction_version: task.current_correction_version,
        current_correction_digest: task.current_correction_digest ?? null,
        effective_version: task.effective_version,
        effective_digest: task.effective_digest ?? null,
        claim_actor_id: task.claim_actor_id ?? null,
        claim_fence: task.claim_fence,
        claim_expires_at: task.claim_expires_at ?? null,
        updated_at: task.updated_at,
        closed_at: task.closed_at ?? null,
    };
} } catch(e) {}
try { function exactReviewCursor(value, expectedFilterDigest, lastTask) {
    if (!/^[A-Za-z0-9_-]{1,4096}$/.test(value))
        return false;
    try {
        const standard = value.replaceAll("-", "+").replaceAll("_", "/");
        const padded = standard + "=".repeat((4 - standard.length % 4) % 4);
        const binary = atob(padded);
        const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
        const source = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
        const decoded = parseStrictJson(source, { maximumDepth: 4, maximumNodes: 16 });
        if (!decoded || typeof decoded !== "object" || Array.isArray(decoded))
            return false;
        const cursor = decoded;
        const fields = new Set(["version", "filter_digest", "confidence", "created_at", "task_id"]);
        const canonical = bytesToBase64(new TextEncoder().encode(canonicalStrictJson(cursor))).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
        return exactObjectFields(cursor, fields)
            && canonical === value
            && cursor.version === "human-review-cursor-v1"
            && cursor.filter_digest === expectedFilterDigest
            && typeof cursor.confidence === "number"
            && Number.isFinite(cursor.confidence)
            && cursor.confidence === lastTask.confidence
            && cursor.created_at === lastTask.created_at
            && cursor.task_id === lastTask.task_id;
    }
    catch {
        return false;
    }
} } catch(e) {}
try { function exactReviewSourceCursor(value, expectedFilterDigest, expectedCollectionDigest, expectedCollectionGeneration, lastSource) {
    if (!/^[A-Za-z0-9_-]{1,4096}$/.test(value))
        return undefined;
    try {
        const standard = value.replaceAll("-", "+").replaceAll("_", "/");
        const padded = standard + "=".repeat((4 - standard.length % 4) % 4);
        const binary = atob(padded);
        const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
        const source = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
        const decoded = parseStrictJson(source, { maximumDepth: 4, maximumNodes: 16 });
        if (!decoded || typeof decoded !== "object" || Array.isArray(decoded))
            return undefined;
        const cursor = decoded;
        const fields = new Set([
            "version", "filter_digest", "collection_digest", "collection_generation",
            "target_kind", "target_digest",
        ]);
        const canonical = bytesToBase64(new TextEncoder().encode(canonicalStrictJson(cursor))).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
        if (!exactObjectFields(cursor, fields)
            || canonical !== value
            || cursor.version !== "human-review-source-cursor-v1"
            || cursor.filter_digest !== expectedFilterDigest
            || typeof cursor.collection_digest !== "string"
            || !/^[0-9a-f]{64}$/.test(cursor.collection_digest)
            || positiveInteger(cursor.collection_generation) === undefined
            || expectedCollectionDigest !== undefined
                && cursor.collection_digest !== expectedCollectionDigest
            || expectedCollectionGeneration !== undefined
                && cursor.collection_generation !== expectedCollectionGeneration
            || cursor.target_kind !== lastSource.target_kind
            || cursor.target_digest !== lastSource.target_digest)
            return undefined;
        return {
            collectionDigest: cursor.collection_digest,
            collectionGeneration: cursor.collection_generation,
        };
    }
    catch {
        return undefined;
    }
} } catch(e) {}
try { function strictSkillResponse(value, httpOk, expectedSkill, expectedOperation) {
    if (!value || typeof value !== "object" || Array.isArray(value)) {
        throw new Error("MULTIMODAL_RESPONSE_INVALID");
    }
    const response = value;
    const allowed = new Set([
        "schema_version", "skill", "operation", "status", "code", "retryable",
        "trace_id", "request_digest", "implementation_state", "external_evidence",
        "certification", "output", "result_digest",
    ]);
    if (Object.keys(response).some((key) => !allowed.has(key))) {
        throw new Error("MULTIMODAL_RESPONSE_FIELDS_INVALID");
    }
    const status = response.status;
    if (typeof status !== "string" || ![
        "SUCCEEDED", "PARTIAL", "BLOCKED", "FAILED", "NOT_APPLICABLE", "NOT_RUN_EXTERNAL",
    ].includes(status.toUpperCase())) {
        throw new Error("MULTIMODAL_RESPONSE_STATUS_INVALID");
    }
    if (response.retryable !== undefined && typeof response.retryable !== "boolean") {
        throw new Error("MULTIMODAL_RESPONSE_RETRYABLE_INVALID");
    }
    for (const key of ["code", "trace_id"]) {
        if (response[key] !== undefined && !boundedOpaque(response[key])) {
            throw new Error("MULTIMODAL_RESPONSE_FIELD_INVALID");
        }
    }
    if (httpOk && (!response.output || typeof response.output !== "object" || Array.isArray(response.output))) {
        throw new Error("MULTIMODAL_RESPONSE_OUTPUT_INVALID");
    }
    if (!httpOk) {
        const errorFields = new Set([
            "schema_version", "status", "code", "retryable", "trace_id",
            "external_evidence", "certification", "result_digest",
        ]);
        if (Object.keys(response).length !== errorFields.size
            || Object.keys(response).some((key) => !errorFields.has(key))
            || response.schema_version !== "1.0.0"
            || !["BLOCKED", "FAILED"].includes(String(response.status))
            || typeof response.code !== "string"
            || !/^[A-Z][A-Z0-9_:-]{0,127}$/.test(response.code)
            || typeof response.retryable !== "boolean"
            || !boundedOpaque(response.trace_id)
            || response.external_evidence !== "NOT_RUN"
            || response.certification !== "NOT_CERTIFIED"
            || typeof response.result_digest !== "string"
            || !/^[0-9a-f]{64}$/.test(response.result_digest)) {
            throw new Error("MULTIMODAL_ERROR_RESPONSE_INVALID");
        }
        return response;
    }
    const fullFields = new Set([
        "schema_version", "skill", "operation", "status", "retryable", "trace_id",
        "request_digest", "implementation_state", "external_evidence", "certification",
        "output", "result_digest",
    ]);
    if (response.code !== undefined)
        fullFields.add("code");
    if (Object.keys(response).length !== fullFields.size
        || Object.keys(response).some((key) => !fullFields.has(key))
        || response.schema_version !== "1.0.0"
        || response.skill !== expectedSkill
        || response.operation !== expectedOperation
        || !["SUCCEEDED", "PARTIAL", "BLOCKED", "FAILED", "NOT_APPLICABLE", "NOT_RUN_EXTERNAL"]
            .includes(String(response.status))
        || typeof response.retryable !== "boolean"
        || !boundedOpaque(response.trace_id)
        || typeof response.request_digest !== "string"
        || !/^[0-9a-f]{64}$/.test(response.request_digest)
        || !["CODE_IMPLEMENTED_LOCAL", "BRIDGE_REQUIRED"].includes(String(response.implementation_state))
        || response.external_evidence !== "NOT_RUN"
        || response.certification !== "NOT_CERTIFIED"
        || typeof response.result_digest !== "string"
        || !/^[0-9a-f]{64}$/.test(response.result_digest)
        || (response.code !== undefined && (typeof response.code !== "string" || !/^[A-Z][A-Z0-9_:-]{0,127}$/.test(response.code)))
        || (["BLOCKED", "FAILED"].includes(String(response.status)) && response.code === undefined)) {
        throw new Error("MULTIMODAL_RESPONSE_ENVELOPE_INVALID");
    }
    return response;
} } catch(e) {}
try { async function readSkillResponse(response, expectedSkill, expectedOperation) {
    const mediaType = response.headers.get("content-type")?.split(";", 1)[0].trim().toLowerCase();
    if (mediaType !== "application/json")
        throw new Error("MULTIMODAL_RESPONSE_MEDIA_TYPE_INVALID");
    const declared = response.headers.get("content-length");
    const contentEncoding = response.headers.get("content-encoding")?.trim().toLowerCase();
    if (declared && (!/^[0-9]{1,10}$/.test(declared) || Number(declared) > maximumSkillResponseBytes)) {
        throw new Error("MULTIMODAL_RESPONSE_TOO_LARGE");
    }
    if (!response.body)
        throw new Error("MULTIMODAL_RESPONSE_INVALID");
    const reader = response.body.getReader();
    const chunks = [];
    let observed = 0;
    try {
        while (true) {
            const { done, value } = await reader.read();
            if (done)
                break;
            observed += value.byteLength;
            if (observed > maximumSkillResponseBytes) {
                try {
                    await reader.cancel("MULTIMODAL_RESPONSE_TOO_LARGE");
                }
                catch {
                    // The size violation remains authoritative if the peer closed first.
                }
                throw new Error("MULTIMODAL_RESPONSE_TOO_LARGE");
            }
            chunks.push(value);
        }
    }
    finally {
        reader.releaseLock();
    }
    if (declared && (!contentEncoding || contentEncoding === "identity") && observed !== Number(declared)) {
        throw new Error("MULTIMODAL_RESPONSE_SIZE_INVALID");
    }
    const bytes = new Uint8Array(observed);
    let offset = 0;
    for (const chunk of chunks) {
        bytes.set(chunk, offset);
        offset += chunk.byteLength;
    }
    let source;
    try {
        source = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    }
    catch {
        throw new Error("MULTIMODAL_RESPONSE_JSON_INVALID");
    }
    try {
        const payload = strictSkillResponse(parseStrictJson(source, { maximumDepth: 32, maximumNodes: 250_000 }), response.ok, expectedSkill, expectedOperation);
        const unsigned = { ...payload };
        delete unsigned.result_digest;
        const expectedDigest = await sha256(new TextEncoder().encode(canonicalStrictJson(unsigned)).buffer);
        if (payload.result_digest !== expectedDigest) {
            throw new Error("MULTIMODAL_RESPONSE_DIGEST_INVALID");
        }
        return payload;
    }
    catch (error) {
        if (error instanceof StrictJsonError) {
            throw new Error(`MULTIMODAL_RESPONSE_${error.code}`);
        }
        throw error;
    }
} } catch(e) {}
try { async function executeSkill(projectId, skill, operation, input, idempotencyKey) {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort("MULTIMODAL_REQUEST_TIMEOUT"), skillRequestTimeoutMs);
    try {
        const unsigned = {
            schema_version: browserRequestSchemaVersion,
            skill,
            operation,
            projectId,
            input,
        };
        const requestDigest = await sha256(new TextEncoder().encode(canonicalStrictJson(unsigned)).buffer);
        const response = await fetch(webBffRoute, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Idempotency-Key": idempotencyKey,
            },
            body: canonicalStrictJson({ ...unsigned, request_digest: requestDigest }),
            signal: controller.signal,
        });
        const payload = await readSkillResponse(response, skill, operation);
        if (!response.ok) {
            const error = new Error(responseString(payload, "code", "error_code") ?? "MULTIMODAL_REQUEST_FAILED");
            Object.assign(error, { payload });
            throw error;
        }
        const state = String(payload.status ?? payload.state ?? "").toUpperCase();
        if (["BLOCKED", "FAILED"].includes(state)) {
            const error = new Error(responseString(payload, "code", "error_code") ?? "MULTIMODAL_OPERATION_BLOCKED");
            Object.assign(error, { payload });
            throw error;
        }
        return payload;
    }
    catch (error) {
        if (controller.signal.aborted)
            throw new Error("MULTIMODAL_REQUEST_TIMEOUT");
        throw error;
    }
    finally {
        window.clearTimeout(timer);
    }
} } catch(e) {}
try { function phaseFrom(response) {
    const status = (response.status ?? response.state ?? responseString(response, "status", "state", "asset_status", "result_status", "job_status") ?? "").toUpperCase();
    if (["READY", "SUCCEEDED", "PASSED", "COMPLETED", "CODE_IMPLEMENTED_LOCAL"].includes(status))
        return "READY";
    if (["PROCESSING", "RUNNING", "PENDING", "QUEUED", "RETRYING"].includes(status))
        return "PROCESSING";
    if (["PARTIAL", "PARTIAL_READY", "PARTIALLY_READY", "NEEDS_REVIEW", "NOT_RUN", "NOT_RUN_EXTERNAL"].includes(status))
        return "NEEDS_REVIEW";
    if (status.includes("QUARANTIN"))
        return "QUARANTINED";
    return "BLOCKED";
} } catch(e) {}
try { function failureDetails(error, fallback) {
    const payload = error?.payload;
    const code = payload
        ? responseString(payload, "code", "error_code") ?? fallback
        : error instanceof Error
            ? error.message
            : fallback;
    const status = `${payload?.status ?? ""} ${payload?.state ?? ""} ${code}`.toUpperCase();
    return {
        payload,
        code,
        quarantined: status.includes("QUARANTIN"),
        retryable: payload?.retryable,
        traceId: payload ? responseString(payload, "trace_id") : undefined,
    };
} } catch(e) {}

Component({
  options: {
    multipleSlots: false,
    styleIsolation: "apply-shared",
  },
  properties: {
  },
  data: {
    projectId: "default-project",
    directText: "",
    assets: [],
    recoveryRecordCount: 0,
    legacyRecoveryCount: 0,
    recoveryStoreReady: false,
    recoveryStoreError: "",
    busy: false,
    reviewBusy: false,
    feedback: "",
    treeQuery: "",
    packagePreview: null,
    packagePage: null,
    packagePageCursors: [null],
    packagePageIndex: 0,
    estimate: null,
    estimateBusy: false,
    correction: "",
    correctionTouched: false,
    correctionTarget: "",
    reviewTasks: [],
    reviewSources: [],
    selectedReviewSourceKey: "",
    selectedReviewTaskId: "",
    reviewTargetKind: "TEXT",
    reviewTargetLocator: "",
    reviewOriginalValue: "",
    reviewConfidence: "0.5",
    reviewReason: "USER_REVIEW",
    reviewPropagation: null,
    reviewCurrentCorrection: null,
    fileInput: {"current":null},
    folderInput: {"current":null},
    fileAdditionLock: {"current":null},
    fileAdditionOwner: {"current":null},
    selectionCapacity: {"current":null},
    recoveryByScope: {"current":null},
    recoveryLoad: {"current":null},
    reviewClaims: {},
    reviewIdentityScope: "",
    legacyReviewClaimDiscarded: false,
    reviewEnqueueRecoveryCount: 0,
    reviewEnqueueRecoveryError: "",
    reviewClock: 0,
    reviewScopeGeneration: {"current":null},
    reviewRequestOwner: {"current":null},
    reviewEngineScope: {"current":null},
    recoveryIdentityGeneration: {"current":null},
    activeIdentityScope: {"current":null},
    intakeBusyOwner: {"current":null},
    estimateRequestOwner: {"current":null},
    intakeProjectGeneration: {"current":null},
    activeProjectId: {"current":null},
    activeProgressJobKey: null,
    summary: null,
    estimatePlan: null,
    filteredPackagePage: null,
    estimatePlanDocument: null,
  },
  lifetimes: {
    attached() {
      const setProjectId = (val) => { this.setData({ projectId: typeof val === "function" ? val(this.data.projectId) : val }); };
      const setDirectText = (val) => { this.setData({ directText: typeof val === "function" ? val(this.data.directText) : val }); };
      const setAssets = (val) => { this.setData({ assets: typeof val === "function" ? val(this.data.assets) : val }); };
      const setRecoveryRecordCount = (val) => { this.setData({ recoveryRecordCount: typeof val === "function" ? val(this.data.recoveryRecordCount) : val }); };
      const setLegacyRecoveryCount = (val) => { this.setData({ legacyRecoveryCount: typeof val === "function" ? val(this.data.legacyRecoveryCount) : val }); };
      const setRecoveryStoreReady = (val) => { this.setData({ recoveryStoreReady: typeof val === "function" ? val(this.data.recoveryStoreReady) : val }); };
      const setRecoveryStoreError = (val) => { this.setData({ recoveryStoreError: typeof val === "function" ? val(this.data.recoveryStoreError) : val }); };
      const setBusy = (val) => { this.setData({ busy: typeof val === "function" ? val(this.data.busy) : val }); };
      const setReviewBusy = (val) => { this.setData({ reviewBusy: typeof val === "function" ? val(this.data.reviewBusy) : val }); };
      const setFeedback = (val) => { this.setData({ feedback: typeof val === "function" ? val(this.data.feedback) : val }); };
      const setTreeQuery = (val) => { this.setData({ treeQuery: typeof val === "function" ? val(this.data.treeQuery) : val }); };
      const setPackagePreview = (val) => { this.setData({ packagePreview: typeof val === "function" ? val(this.data.packagePreview) : val }); };
      const setPackagePage = (val) => { this.setData({ packagePage: typeof val === "function" ? val(this.data.packagePage) : val }); };
      const setPackagePageCursors = (val) => { this.setData({ packagePageCursors: typeof val === "function" ? val(this.data.packagePageCursors) : val }); };
      const setPackagePageIndex = (val) => { this.setData({ packagePageIndex: typeof val === "function" ? val(this.data.packagePageIndex) : val }); };
      const setEstimate = (val) => { this.setData({ estimate: typeof val === "function" ? val(this.data.estimate) : val }); };
      const setEstimateBusy = (val) => { this.setData({ estimateBusy: typeof val === "function" ? val(this.data.estimateBusy) : val }); };
      const setCorrection = (val) => { this.setData({ correction: typeof val === "function" ? val(this.data.correction) : val }); };
      const setCorrectionTouched = (val) => { this.setData({ correctionTouched: typeof val === "function" ? val(this.data.correctionTouched) : val }); };
      const setCorrectionTarget = (val) => { this.setData({ correctionTarget: typeof val === "function" ? val(this.data.correctionTarget) : val }); };
      const setReviewTasks = (val) => { this.setData({ reviewTasks: typeof val === "function" ? val(this.data.reviewTasks) : val }); };
      const setReviewSources = (val) => { this.setData({ reviewSources: typeof val === "function" ? val(this.data.reviewSources) : val }); };
      const setSelectedReviewSourceKey = (val) => { this.setData({ selectedReviewSourceKey: typeof val === "function" ? val(this.data.selectedReviewSourceKey) : val }); };
      const setSelectedReviewTaskId = (val) => { this.setData({ selectedReviewTaskId: typeof val === "function" ? val(this.data.selectedReviewTaskId) : val }); };
      const setReviewTargetKind = (val) => { this.setData({ reviewTargetKind: typeof val === "function" ? val(this.data.reviewTargetKind) : val }); };
      const setReviewTargetLocator = (val) => { this.setData({ reviewTargetLocator: typeof val === "function" ? val(this.data.reviewTargetLocator) : val }); };
      const setReviewOriginalValue = (val) => { this.setData({ reviewOriginalValue: typeof val === "function" ? val(this.data.reviewOriginalValue) : val }); };
      const setReviewConfidence = (val) => { this.setData({ reviewConfidence: typeof val === "function" ? val(this.data.reviewConfidence) : val }); };
      const setReviewReason = (val) => { this.setData({ reviewReason: typeof val === "function" ? val(this.data.reviewReason) : val }); };
      const setReviewPropagation = (val) => { this.setData({ reviewPropagation: typeof val === "function" ? val(this.data.reviewPropagation) : val }); };
      const setReviewCurrentCorrection = (val) => { this.setData({ reviewCurrentCorrection: typeof val === "function" ? val(this.data.reviewCurrentCorrection) : val }); };
      const setReviewClaims = (val) => { this.setData({ reviewClaims: typeof val === "function" ? val(this.data.reviewClaims) : val }); };
      const setReviewIdentityScope = (val) => { this.setData({ reviewIdentityScope: typeof val === "function" ? val(this.data.reviewIdentityScope) : val }); };
      const setLegacyReviewClaimDiscarded = (val) => { this.setData({ legacyReviewClaimDiscarded: typeof val === "function" ? val(this.data.legacyReviewClaimDiscarded) : val }); };
      const setReviewEnqueueRecoveryCount = (val) => { this.setData({ reviewEnqueueRecoveryCount: typeof val === "function" ? val(this.data.reviewEnqueueRecoveryCount) : val }); };
      const setReviewEnqueueRecoveryError = (val) => { this.setData({ reviewEnqueueRecoveryError: typeof val === "function" ? val(this.data.reviewEnqueueRecoveryError) : val }); };
      const setReviewClock = (val) => { this.setData({ reviewClock: typeof val === "function" ? val(this.data.reviewClock) : val }); };
      const fileInput = { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = { current: { focus: () => {}, scrollIntoView: () => {} } };
      // Lifecycle effect effect_4
      (async () => {
        try {
          let active = true;
    setReviewIdentityScope("");
    setReviewClaims({});
    if (account.status === "loading")
        return () => { active = false; };
    if (account.status === "anonymous") {
        try {
            const scopedKeys = [];
            for (let index = 0; index < sessionStorage.length; index += 1) {
                const key = sessionStorage.key(index);
                if (key && (key === legacyReviewClaimStorageKey
                    || key.startsWith(`${reviewClaimStoragePrefix}:`)
                    || key.startsWith(`${legacyReviewEnqueueStoragePrefix}:`)))
                    scopedKeys.push(key);
            }
            for (const key of scopedKeys)
                sessionStorage.removeItem(key);
        }
        catch {
            // Server-side actor binding remains authoritative when local cleanup fails.
        }
        // V2 enqueue recovery records contain only opaque handles, scoped
        // digests, and idempotency keys. Preserve those records so the same actor
        // can reconcile an UNKNOWN result after signing in again. Legacy V1
        // records contained the exact correction input and are removed above.
        return () => { active = false; };
    }
    const identity = account.status === "authenticated" && account.principal
        ? {
            schema_version: "multimodal-review-browser-scope-v1",
            organization_id: account.principal.organizationId,
            actor_id: account.principal.actorId,
        }
        : {
            schema_version: "multimodal-review-browser-scope-v1",
            local_runner: true,
        };
    void sha256(new TextEncoder().encode(canonicalStrictJson(identity)).buffer).then((digest) => {
        if (active)
            setReviewIdentityScope(`sha256:${digest}`);
    });
    return () => { active = false; };
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
      // Lifecycle effect effect_5
      (async () => {
        try {
          if (!reviewIdentityScope)
        return;
    try {
        const legacy = sessionStorage.getItem(legacyReviewClaimStorageKey);
        setLegacyReviewClaimDiscarded(legacy !== null);
        if (legacy !== null)
            sessionStorage.removeItem(legacyReviewClaimStorageKey);
        const rawEnqueueKeys = [];
        for (let index = 0; index < sessionStorage.length; index += 1) {
            const key = sessionStorage.key(index);
            if (key?.startsWith(`${legacyReviewEnqueueStoragePrefix}:`)) {
                rawEnqueueKeys.push(key);
            }
        }
        for (const key of rawEnqueueKeys)
            sessionStorage.removeItem(key);
    }
    catch {
        setLegacyReviewClaimDiscarded(false);
    }
    setReviewClaims(loadReviewClaims(reviewIdentityScope));
    void updateReviewEnqueueRecoveryState(reviewIdentityScope, projectId);
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
      // Lifecycle effect effect_6
      (async () => {
        try {
          const now = Date.now();
    const boundaries = [
        ...Object.values(reviewClaims).map((claim) => (claim.fence === undefined
            ? claim.created_at + pendingReviewClaimRecoveryMs
            : Date.parse(claim.expires_at))),
        ...reviewTasks.flatMap((task) => (task.claim_expires_at ? [Date.parse(task.claim_expires_at)] : [])),
    ].filter((value) => Number.isFinite(value) && value > now);
    if (boundaries.length === 0)
        return undefined;
    const delay = Math.min(Math.min(...boundaries) - now + 25, 2_147_000_000);
    const timer = window.setTimeout(() => {
        setReviewClock((current) => current + 1);
        if (!reviewIdentityScope)
            return;
        const retained = Object.fromEntries(Object.entries(reviewClaims).filter(([, claim]) => (validReviewClaim(claim, reviewIdentityScope))));
        if (Object.keys(retained).length !== Object.keys(reviewClaims).length
            && persistReviewClaims(retained, reviewIdentityScope)) {
            setReviewClaims(retained);
        }
    }, delay);
    return () => window.clearTimeout(timer);
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
      // Lifecycle effect effect_7
      (async () => {
        try {
          if (reviewIdentityScope)
    void ensureRecoveryStore();
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
      // Lifecycle effect effect_8
      (async () => {
        try {
          if (typeof EventSource === "undefined" || !safeProject(projectId))
        return undefined;
    const jobIds = parseStrictJson(activeProgressJobKey, {
        maximumDepth: 2,
        maximumNodes: maximumBatchAssets + 1,
    });
    if (!Array.isArray(jobIds) || jobIds.length === 0)
        return undefined;
    let active = true;
    const streams = [];
    for (const value of jobIds) {
        if (typeof value !== "string" || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(value)) {
            continue;
        }
        const jobId = value;
        const stream = new EventSource(`/api/multimodal-intake/v1/progress/jobs/${encodeURIComponent(jobId)}`
            + `?projectId=${encodeURIComponent(projectId)}`, { withCredentials: true });
        let streamClosed = false;
        const closeStream = () => {
            if (streamClosed)
                return;
            streamClosed = true;
            stream.close();
        };
        streams.push(stream);
        stream.addEventListener("progress", (rawEvent) => {
            const event = rawEvent;
            void validatedJobProgressEvent(event.data, jobId, event.lastEventId).then((progress) => {
                if (!active)
                    return;
                const state = progress.state;
                const phase = state === "COMPLETED"
                    ? "READY"
                    : ["PARTIAL", "NEEDS_REVIEW"].includes(state)
                        ? "NEEDS_REVIEW"
                        : ["FAILED", "BLOCKED", "CANCELLED"].includes(state)
                            ? "BLOCKED"
                            : "PROCESSING";
                const terminal = ["READY", "NEEDS_REVIEW", "BLOCKED"].includes(phase);
                setAssets((current) => current.map((asset) => (asset.processingJobId === jobId
                    ? {
                        ...asset,
                        phase,
                        progress: terminal ? 100 : Math.max(asset.progress, 80),
                        ...(terminal ? { processingJobId: undefined } : {}),
                    }
                    : asset)));
                if (terminal)
                    closeStream();
            }).catch(() => {
                closeStream();
                if (!active)
                    return;
                setAssets((current) => current.map((asset) => (asset.processingJobId === jobId
                    ? { ...asset, code: "MULTIMODAL_PROGRESS_EVENT_INVALID" }
                    : asset)));
            });
        });
        stream.addEventListener("error", () => {
            // The BFF response is deliberately one bounded batch. Never let native
            // EventSource turn a close or transport failure into an unbounded retry
            // loop; the existing tenant-bound get_session poll is the sole fallback.
            closeStream();
            if (!active)
                return;
            setAssets((current) => current.map((asset) => (asset.processingJobId === jobId
                ? { ...asset, code: "MULTIMODAL_PROGRESS_STREAM_UNAVAILABLE_POLLING" }
                : asset)));
        });
    }
    return () => {
        active = false;
        for (const stream of streams)
            stream.close();
    };
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
      // Lifecycle effect effect_9
      (async () => {
        try {
          let identityGuard;
    try {
        identityGuard = captureIntakeIdentity();
    }
    catch {
        return undefined;
    }
    const sessions = [...new Set(assets
            .filter((asset) => asset.sessionId && !["READY", "QUARANTINED"].includes(asset.phase) && !asset.permanentBlock)
            .map((asset) => asset.sessionId))];
    if (busy || !safeProject(projectId) || sessions.length === 0)
        return undefined;
    let active = true;
    const poll = async () => {
        for (const sessionId of sessions) {
            try {
                const response = await executeGuardedIntakeSkill(identityGuard, projectId, "elmos-multimodal-input-orchestrator", "get_session", { session_id: sessionId }, `mmi-progress-${sessionId}-${Math.floor(Date.now() / 5_000)}`);
                const observed = nestedRecord(response).assets;
                if (!active || !intakeIdentityIsCurrent(identityGuard) || !Array.isArray(observed))
                    continue;
                const byId = new Map(observed
                    .filter((item) => Boolean(item) && typeof item === "object" && !Array.isArray(item) && typeof item.asset_id === "string")
                    .map((item) => [String(item.asset_id), {
                        status: String(item.status ?? "PROCESSING").toUpperCase(),
                        version: positiveInteger(item.version),
                    }]));
                setAssets((current) => {
                    let changed = false;
                    const next = current.map((asset) => {
                        const observedAsset = asset.assetId ? byId.get(asset.assetId) : undefined;
                        if (!observedAsset)
                            return asset;
                        // Corrections create a new immutable asset version. A lagging
                        // session snapshot must never regress that newer local state.
                        if (asset.assetVersion
                            && (!observedAsset.version || observedAsset.version < asset.assetVersion))
                            return asset;
                        const state = observedAsset.status;
                        const phase = state === "READY" || state === "COMPLETED"
                            ? "READY"
                            : state === "NEEDS_REVIEW" || state === "PARTIAL"
                                ? "NEEDS_REVIEW"
                                : state === "QUARANTINED"
                                    ? "QUARANTINED"
                                    : state === "FAILED" || state === "BLOCKED"
                                        ? "BLOCKED"
                                        : "PROCESSING";
                        const progress = ["READY", "NEEDS_REVIEW", "QUARANTINED", "BLOCKED"].includes(phase)
                            ? 100
                            : Math.max(asset.progress, 80);
                        if (phase === asset.phase
                            && progress === asset.progress
                            && (!observedAsset.version || observedAsset.version === asset.assetVersion))
                            return asset;
                        changed = true;
                        return {
                            ...asset,
                            phase,
                            progress,
                            ...(observedAsset.version ? { assetVersion: observedAsset.version } : {}),
                        };
                    });
                    return changed ? next : current;
                });
            }
            catch {
                // Recovery metadata remains authoritative for the next bounded poll.
            }
        }
    };
    void poll();
    const timer = window.setInterval(() => { void poll(); }, 5_000);
    return () => { active = false; window.clearInterval(timer); };
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
      // Lifecycle effect effect_10
      (async () => {
        try {
          estimateRequestOwner.current += 1;
    setEstimate(null);
    setEstimateBusy(false);
        } catch (err) {
          // Handled mount effect
        }
      })().catch(() => {});
    },
    detached() {
    },
  },
  methods: {
    captureIntakeIdentity() {
      const fileInput = this.data.fileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = this.data.folderInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = this.data.fileAdditionLock || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = this.data.fileAdditionOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = this.data.selectionCapacity || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = this.data.recoveryByScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = this.data.recoveryLoad || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = this.data.reviewScopeGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = this.data.reviewRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = this.data.reviewEngineScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = this.data.recoveryIdentityGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = this.data.activeIdentityScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = this.data.intakeBusyOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = this.data.estimateRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = this.data.intakeProjectGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = this.data.activeProjectId || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        const identityScope = activeIdentityScope.current;
    if (!identityScope)
        throw new Error("MULTIMODAL_IDENTITY_SCOPE_UNAVAILABLE");
    return {
        generation: recoveryIdentityGeneration.current,
        identityScope,
        projectGeneration: intakeProjectGeneration.current,
        projectId: activeProjectId.current,
    };
      } catch (err) {
        console.warn("captureIntakeIdentity execution warning:", err);
      }
    },
    intakeIdentityIsCurrent(guard) {
      const fileInput = this.data.fileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = this.data.folderInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = this.data.fileAdditionLock || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = this.data.fileAdditionOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = this.data.selectionCapacity || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = this.data.recoveryByScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = this.data.recoveryLoad || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = this.data.reviewScopeGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = this.data.reviewRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = this.data.reviewEngineScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = this.data.recoveryIdentityGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = this.data.activeIdentityScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = this.data.intakeBusyOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = this.data.estimateRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = this.data.intakeProjectGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = this.data.activeProjectId || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        return guard.generation === recoveryIdentityGeneration.current
        && guard.identityScope === activeIdentityScope.current
        && guard.projectGeneration === intakeProjectGeneration.current
        && guard.projectId === activeProjectId.current;
      } catch (err) {
        console.warn("intakeIdentityIsCurrent execution warning:", err);
      }
    },
    assertIntakeIdentityCurrent(guard) {
      const fileInput = this.data.fileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = this.data.folderInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = this.data.fileAdditionLock || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = this.data.fileAdditionOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = this.data.selectionCapacity || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = this.data.recoveryByScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = this.data.recoveryLoad || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = this.data.reviewScopeGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = this.data.reviewRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = this.data.reviewEngineScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = this.data.recoveryIdentityGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = this.data.activeIdentityScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = this.data.intakeBusyOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = this.data.estimateRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = this.data.intakeProjectGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = this.data.activeProjectId || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        if (!intakeIdentityIsCurrent(guard))
    throw new Error("MULTIMODAL_IDENTITY_SCOPE_CHANGED");
      } catch (err) {
        console.warn("assertIntakeIdentityCurrent execution warning:", err);
      }
    },
    async executeGuardedIntakeSkill(guard, projectAlias, skill, operation, input, idempotencyKey) {
      const fileInput = this.data.fileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = this.data.folderInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = this.data.fileAdditionLock || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = this.data.fileAdditionOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = this.data.selectionCapacity || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = this.data.recoveryByScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = this.data.recoveryLoad || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = this.data.reviewScopeGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = this.data.reviewRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = this.data.reviewEngineScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = this.data.recoveryIdentityGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = this.data.activeIdentityScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = this.data.intakeBusyOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = this.data.estimateRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = this.data.intakeProjectGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = this.data.activeProjectId || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        assertIntakeIdentityCurrent(guard);
    if (projectAlias !== guard.projectId)
        throw new Error("MULTIMODAL_PROJECT_SCOPE_CHANGED");
    const response = await executeSkill(projectAlias, skill, operation, input, idempotencyKey);
    assertIntakeIdentityCurrent(guard);
    return response;
      } catch (err) {
        console.warn("executeGuardedIntakeSkill execution warning:", err);
      }
    },
    publishRecoveryRecords() {
      const fileInput = this.data.fileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = this.data.folderInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = this.data.fileAdditionLock || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = this.data.fileAdditionOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = this.data.selectionCapacity || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = this.data.recoveryByScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = this.data.recoveryLoad || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = this.data.reviewScopeGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = this.data.reviewRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = this.data.reviewEngineScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = this.data.recoveryIdentityGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = this.data.activeIdentityScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = this.data.intakeBusyOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = this.data.estimateRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = this.data.intakeProjectGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = this.data.activeProjectId || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        setRecoveryRecordCount(recoveryByScope.current.size);
      } catch (err) {
        console.warn("publishRecoveryRecords execution warning:", err);
      }
    },
    recoveryRecords(projectAlias, fileFingerprint, engineProjectId) {
      const fileInput = this.data.fileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = this.data.folderInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = this.data.fileAdditionLock || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = this.data.fileAdditionOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = this.data.selectionCapacity || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = this.data.recoveryByScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = this.data.recoveryLoad || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = this.data.reviewScopeGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = this.data.reviewRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = this.data.reviewEngineScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = this.data.recoveryIdentityGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = this.data.activeIdentityScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = this.data.intakeBusyOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = this.data.estimateRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = this.data.intakeProjectGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = this.data.activeProjectId || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        return [...recoveryByScope.current.values()].filter((record) => record.projectId === projectAlias
        && record.fileFingerprint === fileFingerprint
        && (engineProjectId === undefined || record.engineProjectId === engineProjectId));
      } catch (err) {
        console.warn("recoveryRecords execution warning:", err);
      }
    },
    async persistRecovery(record, guard) {
      const fileInput = this.data.fileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = this.data.folderInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = this.data.fileAdditionLock || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = this.data.fileAdditionOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = this.data.selectionCapacity || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = this.data.recoveryByScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = this.data.recoveryLoad || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = this.data.reviewScopeGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = this.data.reviewRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = this.data.reviewEngineScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = this.data.recoveryIdentityGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = this.data.activeIdentityScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = this.data.intakeBusyOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = this.data.estimateRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = this.data.intakeProjectGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = this.data.activeProjectId || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        assertIntakeIdentityCurrent(guard);
    if (!validRecoveryRecord(record)
        || record.identityScope !== guard.identityScope)
        throw new Error("RECOVERY_METADATA_INVALID");
    await putRecoveryValue(record);
    assertIntakeIdentityCurrent(guard);
    recoveryByScope.current.set(recoveryStorageKey(record), record);
    publishRecoveryRecords();
      } catch (err) {
        console.warn("persistRecovery execution warning:", err);
      }
    },
    async clearRecovery(record, guard) {
      const fileInput = this.data.fileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = this.data.folderInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = this.data.fileAdditionLock || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = this.data.fileAdditionOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = this.data.selectionCapacity || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = this.data.recoveryByScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = this.data.recoveryLoad || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = this.data.reviewScopeGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = this.data.reviewRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = this.data.reviewEngineScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = this.data.recoveryIdentityGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = this.data.activeIdentityScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = this.data.intakeBusyOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = this.data.estimateRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = this.data.intakeProjectGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = this.data.activeProjectId || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        assertIntakeIdentityCurrent(guard);
    if (!record.projectId || !record.engineProjectId) {
        throw new Error("RECOVERY_SCOPE_BINDING_MISSING");
    }
    const identity = {
        identityScope: guard.identityScope,
        projectId: record.projectId,
        engineProjectId: record.engineProjectId,
        fileFingerprint: record.fileFingerprint,
    };
    await deleteRecoveryValue(identity);
    assertIntakeIdentityCurrent(guard);
    recoveryByScope.current.delete(recoveryStorageKey(identity));
    publishRecoveryRecords();
      } catch (err) {
        console.warn("clearRecovery execution warning:", err);
      }
    },
    recoveryFromAsset(asset, guard) {
      const fileInput = this.data.fileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = this.data.folderInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = this.data.fileAdditionLock || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = this.data.fileAdditionOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = this.data.selectionCapacity || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = this.data.recoveryByScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = this.data.recoveryLoad || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = this.data.reviewScopeGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = this.data.reviewRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = this.data.reviewEngineScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = this.data.recoveryIdentityGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = this.data.activeIdentityScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = this.data.intakeBusyOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = this.data.estimateRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = this.data.intakeProjectGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = this.data.activeProjectId || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        assertIntakeIdentityCurrent(guard);
    if (!asset.projectId
        || !asset.engineProjectId
        || !asset.sessionAttemptKey) {
        throw new Error("RECOVERY_SCOPE_OR_SESSION_BINDING_MISSING");
    }
    return {
        schemaVersion: 2,
        identityScope: guard.identityScope,
        fileFingerprint: asset.fileFingerprint,
        expectedSize: asset.file.size,
        lastModified: asset.file.lastModified,
        partSize: chunkBytes,
        attemptKey: asset.attemptKey,
        projectId: asset.projectId,
        engineProjectId: asset.engineProjectId,
        sessionAttemptKey: asset.sessionAttemptKey,
        ...(asset.sha256 ? { contentSha256: asset.sha256 } : {}),
        ...(asset.sessionId ? { sessionId: asset.sessionId } : {}),
        ...(asset.uploadSessionId ? { uploadSessionId: asset.uploadSessionId } : {}),
        confirmedPartCount: asset.confirmedPartCount,
        processingAttempt: asset.processingAttempt,
        ...(asset.assetId ? { assetId: asset.assetId } : {}),
        ...(asset.assetVersion ? { assetVersion: asset.assetVersion } : {}),
        role: asset.role,
        modelReadAllowed: asset.modelReadAllowed,
        updatedAt: Date.now(),
    };
      } catch (err) {
        console.warn("recoveryFromAsset execution warning:", err);
      }
    },
    async addFiles(files) {
      const fileInput = this.data.fileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = this.data.folderInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = this.data.fileAdditionLock || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = this.data.fileAdditionOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = this.data.selectionCapacity || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = this.data.recoveryByScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = this.data.recoveryLoad || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = this.data.reviewScopeGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = this.data.reviewRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = this.data.reviewEngineScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = this.data.recoveryIdentityGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = this.data.activeIdentityScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = this.data.intakeBusyOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = this.data.estimateRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = this.data.intakeProjectGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = this.data.activeProjectId || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        if (fileAdditionLock.current) {
        setFeedback("FILE_SELECTION_IN_PROGRESS");
        return;
    }
    const fileOwner = fileAdditionOwner.current + 1;
    fileAdditionOwner.current = fileOwner;
    fileAdditionLock.current = true;
    try {
        let identityGuard;
        try {
            identityGuard = captureIntakeIdentity();
        }
        catch (error) {
            setFeedback(error instanceof Error ? error.message : "MULTIMODAL_IDENTITY_SCOPE_UNAVAILABLE");
            return;
        }
        const selectedFiles = [];
        let selectedBytes = 0;
        for (const file of files) {
            if (selectionCapacity.current.count + selectedFiles.length >= maximumBatchAssets) {
                setFeedback("BATCH_ASSET_COUNT_LIMIT_EXCEEDED");
                return;
            }
            selectedBytes += file.size;
            if (!Number.isSafeInteger(file.size)
                || file.size < 0
                || !Number.isSafeInteger(selectedBytes)
                || selectionCapacity.current.bytes + selectedBytes > maximumBatchBytes) {
                setFeedback("BATCH_BYTE_LIMIT_EXCEEDED");
                return;
            }
            selectedFiles.push(file);
        }
        if (selectedFiles.length === 0)
            return;
        if (!await ensureRecoveryStore()) {
            if (intakeIdentityIsCurrent(identityGuard))
                setFeedback("RECOVERY_STORE_UNAVAILABLE");
            return;
        }
        assertIntakeIdentityCurrent(identityGuard);
        let fingerprinted;
        try {
            fingerprinted = await Promise.all(selectedFiles.map(async (file) => ({ file, fingerprint: await fingerprintFile(file) })));
            assertIntakeIdentityCurrent(identityGuard);
        }
        catch (_error) {
            if (intakeIdentityIsCurrent(identityGuard))
                setFeedback("FILE_FINGERPRINT_FAILED");
            return;
        }
        const invalidRecoveryFingerprints = new Set();
        for (const { file, fingerprint } of fingerprinted) {
            for (const record of recoveryRecords(projectId, fingerprint)) {
                if (record.expectedSize !== file.size
                    || record.lastModified !== file.lastModified
                    || record.partSize !== chunkBytes) {
                    try {
                        await clearRecovery(record, identityGuard);
                    }
                    catch (_error) {
                        if (intakeIdentityIsCurrent(identityGuard)) {
                            setFeedback("RECOVERY_STORE_WRITE_FAILED");
                        }
                        return;
                    }
                    invalidRecoveryFingerprints.add(fingerprint);
                }
            }
        }
        const batchFingerprintCounts = new Map();
        for (const { fingerprint } of fingerprinted) {
            batchFingerprintCounts.set(fingerprint, (batchFingerprintCounts.get(fingerprint) ?? 0) + 1);
        }
        const existingFingerprints = new Set(assets.map((asset) => asset.fileFingerprint));
        const collisionFingerprints = new Set(fingerprinted
            .map(({ fingerprint }) => fingerprint)
            .filter((fingerprint) => (batchFingerprintCounts.get(fingerprint) ?? 0) > 1 || existingFingerprints.has(fingerprint)));
        const hasCollision = collisionFingerprints.size > 0;
        assertIntakeIdentityCurrent(identityGuard);
        if (hasCollision)
            setFeedback("FILE_FINGERPRINT_COLLISION");
        selectionCapacity.current = {
            count: selectionCapacity.current.count + fingerprinted.length,
            bytes: selectionCapacity.current.bytes + selectedBytes,
        };
        setAssets((current) => {
            const protectedCurrent = current.map((asset) => collisionFingerprints.has(asset.fileFingerprint)
                ? {
                    ...asset,
                    phase: "BLOCKED",
                    progress: 100,
                    permanentBlock: true,
                    recoveryCandidate: false,
                    recoveryAttached: false,
                    code: "FILE_FINGERPRINT_COLLISION",
                }
                : asset);
            const additions = fingerprinted
                .map(({ file, fingerprint }, index) => {
                const collision = collisionFingerprints.has(fingerprint);
                const recoveries = collision ? [] : recoveryRecords(projectId, fingerprint);
                const code = invalidRecoveryFingerprints.has(fingerprint)
                    ? "RECOVERY_METADATA_MISMATCH"
                    : file.size <= 0
                        ? "EMPTY_FILE_NOT_ALLOWED"
                        : file.size > maximumProcessableAssetBytes
                            ? "FILE_EXCEEDS_64_MIB_PROCESSING_LIMIT"
                            : collision
                                ? "FILE_FINGERPRINT_COLLISION"
                                : supportedExtensions.has(extensionOf(file))
                                    ? undefined
                                    : "FILE_TYPE_NOT_IN_V1_ALLOWLIST";
                return {
                    key: `${fingerprint}:${index}:${crypto.randomUUID()}`,
                    fileFingerprint: fingerprint,
                    attemptKey: crypto.randomUUID(),
                    projectId: recoveries.length > 0 ? projectId : undefined,
                    file,
                    relativePath: relativePath(file),
                    phase: code ? "BLOCKED" : "SELECTED",
                    progress: 0,
                    permanentBlock: Boolean(code),
                    recoveryCandidate: recoveries.length > 0,
                    recoveryAttached: false,
                    confirmedPartCount: 0,
                    processingAttempt: 0,
                    role: recoveries[0]?.role ?? "PRIMARY",
                    modelReadAllowed: recoveries[0]?.modelReadAllowed ?? true,
                    code,
                };
            });
            return [...protectedCurrent, ...additions];
        });
    }
    catch (error) {
        // A scope change mid-addition discards the selection. Report it instead of
        // dropping the files silently: the file input value is already cleared, so
        // nothing retries on its own.
        setFeedback(error instanceof Error ? error.message : "FILE_SELECTION_FAILED");
    }
    finally {
        if (fileAdditionOwner.current === fileOwner)
            fileAdditionLock.current = false;
    }
      } catch (err) {
        console.warn("addFiles execution warning:", err);
      }
    },
    update(key, patch) {
      const fileInput = this.data.fileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = this.data.folderInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = this.data.fileAdditionLock || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = this.data.fileAdditionOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = this.data.selectionCapacity || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = this.data.recoveryByScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = this.data.recoveryLoad || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = this.data.reviewScopeGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = this.data.reviewRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = this.data.reviewEngineScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = this.data.recoveryIdentityGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = this.data.activeIdentityScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = this.data.intakeBusyOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = this.data.estimateRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = this.data.intakeProjectGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = this.data.activeProjectId || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        setAssets((current) => current.map((asset) => asset.key === key ? { ...asset, ...patch } : asset));
      } catch (err) {
        console.warn("update execution warning:", err);
      }
    },
    updateMany(keys, patch) {
      const fileInput = this.data.fileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = this.data.folderInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = this.data.fileAdditionLock || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = this.data.fileAdditionOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = this.data.selectionCapacity || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = this.data.recoveryByScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = this.data.recoveryLoad || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = this.data.reviewScopeGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = this.data.reviewRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = this.data.reviewEngineScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = this.data.recoveryIdentityGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = this.data.activeIdentityScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = this.data.intakeBusyOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = this.data.estimateRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = this.data.intakeProjectGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = this.data.activeProjectId || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        const selected = new Set(keys);
    setAssets((current) => current.map((asset) => selected.has(asset.key) ? { ...asset, ...patch } : asset));
      } catch (err) {
        console.warn("updateMany execution warning:", err);
      }
    },
    async refreshProcessingEstimate() {
      const fileInput = this.data.fileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = this.data.folderInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = this.data.fileAdditionLock || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = this.data.fileAdditionOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = this.data.selectionCapacity || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = this.data.recoveryByScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = this.data.recoveryLoad || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = this.data.reviewScopeGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = this.data.reviewRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = this.data.reviewEngineScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = this.data.recoveryIdentityGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = this.data.activeIdentityScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = this.data.intakeBusyOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = this.data.estimateRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = this.data.intakeProjectGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = this.data.activeProjectId || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        if (!safeProject(projectId) || estimatePlan.stages.length === 0) {
        setEstimate({
            inputDigest: "",
            status: "BLOCKED",
            code: "ESTIMATION_STAGES_REQUIRED",
        });
        return;
    }
    let identityGuard;
    try {
        identityGuard = captureIntakeIdentity();
    }
    catch (error) {
        setEstimate({
            inputDigest: "",
            status: "BLOCKED",
            code: error instanceof Error ? error.message : "MULTIMODAL_IDENTITY_SCOPE_UNAVAILABLE",
        });
        return;
    }
    const owner = estimateRequestOwner.current + 1;
    estimateRequestOwner.current = owner;
    setEstimateBusy(true);
    setEstimate(null);
    try {
        const inputDigest = await sha256(new TextEncoder().encode(estimatePlanDocument).buffer);
        if (owner !== estimateRequestOwner.current)
            return;
        assertIntakeIdentityCurrent(identityGuard);
        const response = await executeGuardedIntakeSkill(identityGuard, projectId, "elmos-processing-cost-and-eta-estimation", "estimate", estimatePlan, `mmi-cost-estimate-${inputDigest.slice(0, 40)}`);
        if (owner !== estimateRequestOwner.current)
            return;
        setEstimate(processingEstimate(response, `sha256:${inputDigest}`));
    }
    catch (error) {
        if (owner !== estimateRequestOwner.current || !intakeIdentityIsCurrent(identityGuard))
            return;
        const failure = failureDetails(error, "PROCESSING_ESTIMATE_FAILED");
        setEstimate({
            inputDigest: "",
            status: "BLOCKED",
            code: failure.code,
        });
    }
    finally {
        if (owner === estimateRequestOwner.current)
            setEstimateBusy(false);
    }
      } catch (err) {
        console.warn("refreshProcessingEstimate execution warning:", err);
      }
    },
    async uploadAsset(asset, sessionId, projectAlias, identityGuard) {
      const fileInput = this.data.fileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = this.data.folderInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = this.data.fileAdditionLock || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = this.data.fileAdditionOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = this.data.selectionCapacity || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = this.data.recoveryByScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = this.data.recoveryLoad || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = this.data.reviewScopeGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = this.data.reviewRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = this.data.reviewEngineScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = this.data.recoveryIdentityGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = this.data.activeIdentityScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = this.data.intakeBusyOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = this.data.estimateRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = this.data.intakeProjectGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = this.data.activeProjectId || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        assertIntakeIdentityCurrent(identityGuard);
    if (asset.permanentBlock)
        throw new Error(asset.code ?? "ASSET_PERMANENTLY_BLOCKED");
    if (asset.sessionId && asset.sessionId !== sessionId)
        throw new Error("INPUT_SESSION_ID_CHANGED");
    if (asset.projectId !== projectAlias)
        throw new Error("ASSET_PROJECT_BINDING_MISMATCH");
    update(asset.key, {
        sessionId,
        phase: "HASHING",
        progress: 2,
        code: undefined,
        response: undefined,
        traceId: undefined,
    });
    const digest = await sha256FileOffMainThread(asset.file);
    assertIntakeIdentityCurrent(identityGuard);
    if (asset.sha256 && asset.sha256 !== digest) {
        await clearRecovery(asset, identityGuard);
        throw new Error("RECOVERY_CONTENT_HASH_MISMATCH");
    }
    update(asset.key, { sha256: digest, phase: "UPLOADING", progress: 5 });
    let recoveryAsset = { ...asset, sessionId, sha256: digest };
    await persistRecovery(recoveryFromAsset(recoveryAsset, identityGuard), identityGuard);
    if (recoveryAsset.assetId) {
        update(asset.key, { phase: "PROCESSING", progress: 78 });
        return recoveryAsset.assetId;
    }
    const started = await executeGuardedIntakeSkill(identityGuard, projectAlias, "elmos-secure-resumable-upload", "start", {
        session_id: sessionId,
        display_name: asset.relativePath,
        expected_size: asset.file.size,
        expected_sha256: digest,
        declared_media_type: asset.file.type || "application/octet-stream",
        part_size: chunkBytes,
    }, `mmi-${asset.attemptKey}-start`);
    const uploadSessionId = responseString(started, "upload_session_id", "session_id", "upload_id");
    if (!uploadSessionId)
        throw new Error("UPLOAD_SESSION_ID_MISSING");
    if (asset.uploadSessionId && asset.uploadSessionId !== uploadSessionId) {
        throw new Error("UPLOAD_SESSION_ID_CHANGED");
    }
    update(asset.key, { uploadSessionId });
    recoveryAsset = { ...recoveryAsset, uploadSessionId };
    await persistRecovery(recoveryFromAsset(recoveryAsset, identityGuard), identityGuard);
    const partCount = Math.max(1, Math.ceil(asset.file.size / chunkBytes));
    if (recoveryAsset.confirmedPartCount > partCount) {
        await clearRecovery(recoveryAsset, identityGuard);
        throw new Error("RECOVERY_CONFIRMED_PROGRESS_INVALID");
    }
    for (let part = recoveryAsset.confirmedPartCount; part < partCount; part += 1) {
        const start = part * chunkBytes;
        const chunk = new Uint8Array(await asset.file.slice(start, Math.min(asset.file.size, start + chunkBytes)).arrayBuffer());
        const chunkDigest = await sha256(chunk.slice().buffer);
        assertIntakeIdentityCurrent(identityGuard);
        await executeGuardedIntakeSkill(identityGuard, projectAlias, "elmos-secure-resumable-upload", "upload_part", {
            upload_session_id: uploadSessionId,
            part_number: part,
            byte_offset: start,
            sha256: chunkDigest,
            data_b64: bytesToBase64(chunk),
        }, `mmi-${asset.attemptKey}-part-${part + 1}`);
        recoveryAsset = { ...recoveryAsset, confirmedPartCount: part + 1 };
        await persistRecovery(recoveryFromAsset(recoveryAsset, identityGuard), identityGuard);
        update(asset.key, {
            confirmedPartCount: part + 1,
            progress: 5 + Math.round(((part + 1) / partCount) * 60),
        });
    }
    update(asset.key, { phase: "VALIDATING", progress: 70 });
    const committed = await executeGuardedIntakeSkill(identityGuard, projectAlias, "elmos-secure-resumable-upload", "commit", { upload_session_id: uploadSessionId, expected_sha256: digest }, `mmi-${asset.attemptKey}-commit`);
    const assetId = responseString(committed, "asset_id", "asset_version_id", "object_id");
    if (!assetId)
        throw new Error("ASSET_ID_MISSING");
    if (asset.assetId && asset.assetId !== assetId)
        throw new Error("ASSET_ID_CHANGED");
    const committedAsset = outputRecord(committed, "asset");
    const assetVersion = positiveInteger(committedAsset?.version) ?? asset.assetVersion;
    recoveryAsset = { ...recoveryAsset, assetId, assetVersion };
    await persistRecovery(recoveryFromAsset(recoveryAsset, identityGuard), identityGuard);
    update(asset.key, {
        assetId,
        assetVersion,
        phase: "PROCESSING",
        progress: 78,
    });
    return assetId;
      } catch (err) {
        console.warn("uploadAsset execution warning:", err);
      }
    },
    async processAll() {
      const fileInput = this.data.fileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = this.data.folderInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = this.data.fileAdditionLock || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = this.data.fileAdditionOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = this.data.selectionCapacity || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = this.data.recoveryByScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = this.data.recoveryLoad || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = this.data.reviewScopeGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = this.data.reviewRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = this.data.reviewEngineScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = this.data.recoveryIdentityGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = this.data.activeIdentityScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = this.data.intakeBusyOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = this.data.estimateRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = this.data.intakeProjectGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = this.data.activeProjectId || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        let identityGuard;
    try {
        identityGuard = captureIntakeIdentity();
    }
    catch (error) {
        setFeedback(error instanceof Error ? error.message : "MULTIMODAL_IDENTITY_SCOPE_UNAVAILABLE");
        return;
    }
    if (!recoveryStoreReady && !await ensureRecoveryStore()) {
        if (intakeIdentityIsCurrent(identityGuard))
            setFeedback("RECOVERY_STORE_UNAVAILABLE");
        return;
    }
    assertIntakeIdentityCurrent(identityGuard);
    if (!safeProject(projectId)) {
        setFeedback("项目 ID 仅允许字母、数字、点、下划线、冒号和短横线。");
        return;
    }
    const fingerprintCounts = new Map();
    for (const asset of assets) {
        fingerprintCounts.set(asset.fileFingerprint, (fingerprintCounts.get(asset.fileFingerprint) ?? 0) + 1);
    }
    const duplicateFingerprints = new Set([...fingerprintCounts]
        .filter(([, count]) => count > 1)
        .map(([fingerprint]) => fingerprint));
    if (duplicateFingerprints.size > 0) {
        setAssets((current) => current.map((asset) => duplicateFingerprints.has(asset.fileFingerprint)
            ? {
                ...asset,
                phase: "BLOCKED",
                progress: 100,
                permanentBlock: true,
                recoveryCandidate: false,
                recoveryAttached: false,
                code: "FILE_FINGERPRINT_COLLISION",
            }
            : asset));
        setFeedback("FILE_FINGERPRINT_COLLISION");
        return;
    }
    const projectAlias = projectId;
    const retryable = assets.filter((asset) => !asset.permanentBlock
        && asset.role !== "IGNORE"
        && asset.modelReadAllowed
        && ["SELECTED", "BLOCKED", "NEEDS_REVIEW"].includes(asset.phase));
    if (retryable.length === 0) {
        setFeedback("没有可接入或可恢复的条目；永久阻断的空文件、超限文件和不支持格式不会重试。");
        return;
    }
    if (retryable.some((asset) => asset.projectId && asset.projectId !== projectAlias)) {
        setFeedback("ASSET_PROJECT_BINDING_MISMATCH");
        return;
    }
    const busyOwner = intakeBusyOwner.current + 1;
    intakeBusyOwner.current = busyOwner;
    setBusy(true);
    setFeedback("");
    const newSessionAttemptKey = crypto.randomUUID();
    let candidates = retryable.map((asset) => {
        return {
            ...asset,
            projectId: asset.projectId ?? projectAlias,
            sessionAttemptKey: asset.sessionAttemptKey
                ?? newSessionAttemptKey,
        };
    });
    const newlyAssigned = retryable
        .filter((asset) => !asset.sessionAttemptKey && !asset.recoveryCandidate)
        .map((asset) => asset.key);
    if (newlyAssigned.length > 0) {
        updateMany(newlyAssigned, { projectId: projectAlias, sessionAttemptKey: newSessionAttemptKey });
    }
    const missingProjectBinding = retryable
        .filter((asset) => asset.sessionAttemptKey && !asset.projectId)
        .map((asset) => asset.key);
    if (missingProjectBinding.length > 0)
        updateMany(missingProjectBinding, { projectId: projectAlias });
    const bootstrapAttemptKey = candidates[0].sessionAttemptKey;
    if (!bootstrapAttemptKey) {
        setFeedback("INPUT_SESSION_ATTEMPT_KEY_MISSING");
        setBusy(false);
        return;
    }
    try {
        let engineProjectId = "";
        try {
            const bootstrapped = await executeGuardedIntakeSkill(identityGuard, projectAlias, "elmos-multimodal-input-orchestrator", "bootstrap_project", {}, `mmi-${bootstrapAttemptKey}-bootstrap`);
            engineProjectId = responseString(bootstrapped, "project_id", "engine_project_id") ?? "";
            if (!boundedOpaque(engineProjectId))
                throw new Error("ENGINE_PROJECT_SCOPE_MISSING");
        }
        catch (error) {
            if (!intakeIdentityIsCurrent(identityGuard))
                return;
            const failure = failureDetails(error, "PROJECT_BOOTSTRAP_FAILED");
            updateMany(candidates.map((asset) => asset.key), {
                phase: failure.quarantined ? "QUARANTINED" : "BLOCKED",
                progress: 100,
                permanentBlock: failure.quarantined,
                code: failure.code,
                traceId: failure.traceId,
                response: failure.payload,
            });
            setFeedback(failure.code);
            return;
        }
        const scopeMismatches = candidates.filter((asset) => {
            if (!asset.recoveryCandidate && !asset.recoveryAttached)
                return false;
            return recoveryRecords(projectAlias, asset.fileFingerprint, engineProjectId).length !== 1;
        });
        if (scopeMismatches.length > 0) {
            const mismatchedKeys = new Set(scopeMismatches.map((asset) => asset.key));
            for (const asset of candidates) {
                if (!mismatchedKeys.has(asset.key)) {
                    update(asset.key, {
                        phase: "BLOCKED",
                        progress: 100,
                        code: "RECOVERY_BATCH_ENGINE_PROJECT_SCOPE_MISMATCH",
                    });
                    continue;
                }
                update(asset.key, {
                    attemptKey: crypto.randomUUID(),
                    engineProjectId: undefined,
                    sessionAttemptKey: undefined,
                    sessionId: undefined,
                    sha256: undefined,
                    uploadSessionId: undefined,
                    confirmedPartCount: 0,
                    processingAttempt: 0,
                    assetId: undefined,
                    assetVersion: undefined,
                    phase: "BLOCKED",
                    progress: 100,
                    permanentBlock: true,
                    recoveryCandidate: false,
                    recoveryAttached: false,
                    code: "RECOVERY_ENGINE_PROJECT_SCOPE_MISMATCH",
                });
            }
            setFeedback("RECOVERY_ENGINE_PROJECT_SCOPE_MISMATCH");
            return;
        }
        candidates = candidates.map((asset) => {
            const recovery = asset.recoveryCandidate || asset.recoveryAttached
                ? recoveryRecords(projectAlias, asset.fileFingerprint, engineProjectId)[0]
                : undefined;
            return {
                ...asset,
                attemptKey: recovery?.attemptKey ?? asset.attemptKey,
                projectId: recovery?.projectId ?? asset.projectId,
                engineProjectId,
                sessionAttemptKey: recovery?.sessionAttemptKey ?? asset.sessionAttemptKey,
                sessionId: recovery?.sessionId ?? asset.sessionId,
                confirmedPartCount: recovery?.confirmedPartCount ?? asset.confirmedPartCount,
                sha256: recovery?.contentSha256 ?? asset.sha256,
                uploadSessionId: recovery?.uploadSessionId ?? asset.uploadSessionId,
                assetId: recovery?.assetId ?? asset.assetId,
                assetVersion: recovery?.assetVersion ?? asset.assetVersion,
                role: recovery?.role ?? asset.role,
                modelReadAllowed: recovery?.modelReadAllowed ?? asset.modelReadAllowed,
                processingAttempt: recovery?.processingAttempt ?? asset.processingAttempt,
                recoveryCandidate: false,
                recoveryAttached: true,
            };
        });
        const claimedAssetIds = new Map();
        const identityCollisionKeys = new Set();
        for (const asset of [...assets, ...candidates]) {
            if (!asset.assetId)
                continue;
            const owner = claimedAssetIds.get(asset.assetId);
            if (owner && owner !== asset.key) {
                identityCollisionKeys.add(owner);
                identityCollisionKeys.add(asset.key);
                continue;
            }
            claimedAssetIds.set(asset.assetId, asset.key);
        }
        if (identityCollisionKeys.size > 0) {
            updateMany([...identityCollisionKeys], {
                phase: "BLOCKED",
                progress: 100,
                permanentBlock: true,
                recoveryCandidate: false,
                recoveryAttached: false,
                code: "ASSET_IDENTITY_COLLISION",
            });
            setFeedback("ASSET_IDENTITY_COLLISION");
            return;
        }
        try {
            for (const asset of candidates) {
                await persistRecovery(recoveryFromAsset(asset, identityGuard), identityGuard);
                const partCount = Math.max(1, Math.ceil(asset.file.size / chunkBytes));
                update(asset.key, {
                    attemptKey: asset.attemptKey,
                    projectId: asset.projectId,
                    engineProjectId,
                    sessionAttemptKey: asset.sessionAttemptKey,
                    sessionId: asset.sessionId,
                    sha256: asset.sha256,
                    uploadSessionId: asset.uploadSessionId,
                    confirmedPartCount: asset.confirmedPartCount,
                    processingAttempt: asset.processingAttempt,
                    assetId: asset.assetId,
                    assetVersion: asset.assetVersion,
                    recoveryCandidate: false,
                    recoveryAttached: true,
                    progress: Math.min(69, 5 + Math.round((asset.confirmedPartCount / partCount) * 60)),
                });
            }
        }
        catch (error) {
            if (!intakeIdentityIsCurrent(identityGuard))
                return;
            const failure = failureDetails(error, "RECOVERY_STORE_WRITE_FAILED");
            updateMany(candidates.map((asset) => asset.key), {
                phase: "BLOCKED",
                progress: 100,
                code: failure.code,
                traceId: failure.traceId,
                response: failure.payload,
            });
            setFeedback(failure.code);
            return;
        }
        const grouped = new Map();
        for (const asset of candidates) {
            const sessionAttemptKey = asset.sessionAttemptKey;
            if (!sessionAttemptKey)
                continue;
            const groupKey = asset.sessionId
                ? `session:${asset.sessionId}`
                : `attempt:${sessionAttemptKey}:${asset.role}`;
            const group = grouped.get(groupKey) ?? {
                sessionAttemptKey,
                sessionId: asset.sessionId,
                role: asset.role,
                assets: [],
            };
            if (group.role !== asset.role)
                throw new Error("SESSION_ROLE_SCOPE_MISMATCH");
            group.assets.push(asset);
            grouped.set(groupKey, group);
        }
        const resolved = [];
        for (const group of grouped.values()) {
            try {
                let sessionId = group.sessionId;
                if (!sessionId) {
                    const created = await executeGuardedIntakeSkill(identityGuard, projectAlias, "elmos-multimodal-input-orchestrator", "create_session", { requested_role: group.role }, `mmi-${group.sessionAttemptKey}-session`);
                    sessionId = responseString(created, "session_id") ?? "";
                    if (!sessionId)
                        throw new Error("INPUT_SESSION_ID_MISSING");
                    updateMany(group.assets.map((asset) => asset.key), { sessionId });
                    for (const asset of group.assets) {
                        await persistRecovery(recoveryFromAsset({ ...asset, sessionId }, identityGuard), identityGuard);
                    }
                }
                resolved.push({
                    sessionAttemptKey: group.sessionAttemptKey,
                    sessionId,
                    assets: group.assets.map((asset) => ({ ...asset, sessionId })),
                });
            }
            catch (error) {
                if (!intakeIdentityIsCurrent(identityGuard))
                    return;
                const failure = failureDetails(error, "INPUT_SESSION_CREATION_FAILED");
                updateMany(group.assets.map((asset) => asset.key), {
                    phase: failure.quarantined ? "QUARANTINED" : "BLOCKED",
                    progress: 100,
                    permanentBlock: failure.quarantined,
                    code: failure.code,
                    traceId: failure.traceId,
                    response: failure.payload,
                });
            }
        }
        const uploadedGroups = [];
        for (const group of resolved) {
            const uploaded = new Map();
            for (const asset of group.assets) {
                try {
                    const assetId = await uploadAsset(asset, group.sessionId, projectAlias, identityGuard);
                    const owner = claimedAssetIds.get(assetId);
                    if (owner && owner !== asset.key) {
                        identityCollisionKeys.add(owner);
                        identityCollisionKeys.add(asset.key);
                        continue;
                    }
                    claimedAssetIds.set(assetId, asset.key);
                    uploaded.set(asset.key, assetId);
                }
                catch (error) {
                    if (!intakeIdentityIsCurrent(identityGuard))
                        return;
                    const failure = failureDetails(error, "UPLOAD_FAILED");
                    const recoveryInvalid = [
                        "RECOVERY_CONTENT_HASH_MISMATCH",
                        "RECOVERY_CONFIRMED_PROGRESS_INVALID",
                        "RECOVERY_METADATA_INVALID",
                    ].includes(failure.code);
                    const permanentlyBlocked = failure.quarantined || recoveryInvalid || failure.retryable === false;
                    update(asset.key, {
                        phase: failure.quarantined ? "QUARANTINED" : "BLOCKED",
                        progress: 100,
                        permanentBlock: permanentlyBlocked,
                        recoveryCandidate: false,
                        recoveryAttached: permanentlyBlocked ? false : asset.recoveryAttached,
                        ...(recoveryInvalid ? {
                            engineProjectId: undefined,
                            sessionAttemptKey: undefined,
                            sessionId: undefined,
                            sha256: undefined,
                            uploadSessionId: undefined,
                            confirmedPartCount: 0,
                            processingAttempt: 0,
                            assetId: undefined,
                            assetVersion: undefined,
                        } : {}),
                        code: failure.code,
                        traceId: failure.traceId,
                        response: failure.payload,
                    });
                }
            }
            if (uploaded.size > 0)
                uploadedGroups.push({ group, uploaded });
        }
        if (identityCollisionKeys.size > 0) {
            updateMany([...identityCollisionKeys], {
                phase: "BLOCKED",
                progress: 100,
                permanentBlock: true,
                recoveryCandidate: false,
                recoveryAttached: false,
                code: "ASSET_IDENTITY_COLLISION",
            });
            setFeedback("ASSET_IDENTITY_COLLISION");
            return;
        }
        for (const { group, uploaded } of uploadedGroups) {
            try {
                const committedAssetIds = new Set(assets
                    .filter((asset) => asset.sessionId === group.sessionId && asset.assetId)
                    .map((asset) => asset.assetId));
                for (const assetId of uploaded.values())
                    committedAssetIds.add(assetId);
                const membership = [...committedAssetIds].sort().join("\n");
                const membershipDigest = await sha256(new TextEncoder().encode(membership).buffer);
                assertIntakeIdentityCurrent(identityGuard);
                const processingAttempt = Math.max(0, ...group.assets.map((asset) => asset.processingAttempt));
                const processed = await executeGuardedIntakeSkill(identityGuard, projectAlias, "elmos-multimodal-input-orchestrator", "process_session", {
                    session_id: group.sessionId,
                    max_attempts: 3,
                    expected_asset_generation_digest: membershipDigest,
                }, `mmi-${group.sessionAttemptKey}-process-${membershipDigest.slice(0, 32)}-${processingAttempt}`);
                const output = nestedRecord(processed);
                const processingJobId = responseString(processed, "job_id");
                if (!processingJobId
                    || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(processingJobId))
                    throw new Error("WORKFLOW_JOB_ID_MISSING");
                const processedAssets = Array.isArray(output.assets) ? output.assets : [];
                const assetsTruncated = output.assets_truncated === true;
                const resultById = new Map();
                for (const item of processedAssets) {
                    if (item && typeof item === "object" && !Array.isArray(item)) {
                        const entry = item;
                        if (typeof entry.asset_id === "string") {
                            if (resultById.has(entry.asset_id)) {
                                throw new Error("WORKFLOW_DUPLICATE_ASSET_ID");
                            }
                            resultById.set(entry.asset_id, entry);
                        }
                    }
                }
                for (const [key, assetId] of uploaded) {
                    const assetResult = resultById.get(assetId);
                    const assetStatus = assetResult?.status;
                    const assetVersion = positiveInteger(assetResult?.version);
                    const phase = assetResult
                        ? typeof assetStatus === "string"
                            ? phaseFrom({ status: assetStatus })
                            : "NEEDS_REVIEW"
                        : "NEEDS_REVIEW";
                    const assetCode = assetResult
                        ? responseString(assetResult, "failure_code", "error_code", "code")
                        : undefined;
                    const terminal = ["READY", "QUARANTINED"].includes(phase);
                    const nextProcessingAttempt = processingAttempt + 1;
                    update(key, {
                        phase,
                        progress: 100,
                        permanentBlock: phase === "QUARANTINED",
                        recoveryAttached: !terminal,
                        processingAttempt: terminal ? processingAttempt : nextProcessingAttempt,
                        processingJobId: terminal ? undefined : processingJobId,
                        ...(assetVersion ? { assetVersion } : {}),
                        response: processed,
                        traceId: responseString(processed, "trace_id"),
                        code: phase === "READY"
                            ? undefined
                            : !assetResult
                                ? assetsTruncated
                                    ? "WORKFLOW_ASSET_SUMMARY_TRUNCATED"
                                    : "WORKFLOW_ASSET_RESULT_MISSING"
                                : assetCode ?? responseString(processed, "code", "error_code"),
                    });
                    const completedAsset = group.assets.find((asset) => asset.key === key);
                    if (terminal && completedAsset) {
                        await clearRecovery(completedAsset, identityGuard);
                    }
                    else if (completedAsset) {
                        if (!completedAsset.engineProjectId) {
                            throw new Error("RECOVERY_PROCESSING_SCOPE_MISSING");
                        }
                        const records = recoveryRecords(projectAlias, completedAsset.fileFingerprint, completedAsset.engineProjectId);
                        if (records.length !== 1)
                            throw new Error("RECOVERY_PROCESSING_STATE_MISSING");
                        await persistRecovery({
                            ...records[0],
                            processingAttempt: nextProcessingAttempt,
                            ...(assetVersion ? { assetVersion } : {}),
                            updatedAt: Date.now(),
                        }, identityGuard);
                    }
                }
            }
            catch (error) {
                if (!intakeIdentityIsCurrent(identityGuard))
                    return;
                const failure = failureDetails(error, "SESSION_PROCESSING_FAILED");
                const workflowIntegrityFailure = [
                    "WORKFLOW_DUPLICATE_ASSET_ID",
                    "RECOVERY_PROCESSING_STATE_MISSING",
                    "RECOVERY_PROCESSING_SCOPE_MISSING",
                ].includes(failure.code);
                updateMany([...uploaded.keys()], {
                    phase: failure.quarantined ? "QUARANTINED" : "BLOCKED",
                    progress: 100,
                    permanentBlock: failure.quarantined || workflowIntegrityFailure,
                    code: failure.code,
                    traceId: failure.traceId,
                    response: failure.payload,
                });
            }
        }
    }
    finally {
        if (intakeBusyOwner.current === busyOwner)
            setBusy(false);
    }
      } catch (err) {
        console.warn("processAll execution warning:", err);
      }
    },
    addDirectText() {
      const fileInput = this.data.fileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = this.data.folderInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = this.data.fileAdditionLock || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = this.data.fileAdditionOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = this.data.selectionCapacity || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = this.data.recoveryByScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = this.data.recoveryLoad || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = this.data.reviewScopeGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = this.data.reviewRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = this.data.reviewEngineScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = this.data.recoveryIdentityGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = this.data.activeIdentityScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = this.data.intakeBusyOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = this.data.estimateRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = this.data.intakeProjectGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = this.data.activeProjectId || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        const value = directText.trim();
    if (!value)
        return;
    const file = new File([value], `direct-input-${Date.now()}.md`, {
        type: "text/markdown;charset=utf-8",
        lastModified: Date.now(),
    });
    void addFiles([file]);
    setDirectText("");
      } catch (err) {
        console.warn("addDirectText execution warning:", err);
      }
    },
    async buildPackagePreview() {
      const fileInput = this.data.fileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = this.data.folderInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = this.data.fileAdditionLock || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = this.data.fileAdditionOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = this.data.selectionCapacity || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = this.data.recoveryByScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = this.data.recoveryLoad || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = this.data.reviewScopeGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = this.data.reviewRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = this.data.reviewEngineScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = this.data.recoveryIdentityGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = this.data.activeIdentityScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = this.data.intakeBusyOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = this.data.estimateRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = this.data.intakeProjectGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = this.data.activeProjectId || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        if (!safeProject(projectId) || assets.length === 0)
        return;
    let identityGuard;
    try {
        identityGuard = captureIntakeIdentity();
    }
    catch (error) {
        setFeedback(error instanceof Error ? error.message : "MULTIMODAL_IDENTITY_SCOPE_UNAVAILABLE");
        return;
    }
    const busyOwner = intakeBusyOwner.current + 1;
    intakeBusyOwner.current = busyOwner;
    setBusy(true);
    setFeedback("");
    try {
        if (assets.some((asset) => asset.file.size <= 0 || asset.file.size > maximumProcessableAssetBytes)) {
            throw new Error("PREVIEW_REQUIRES_BOUNDED_NON_EMPTY_ASSETS");
        }
        const previewAssets = [];
        for (const asset of assets) {
            const digest = asset.sha256 ?? await sha256FileOffMainThread(asset.file);
            assertIntakeIdentityCurrent(identityGuard);
            if (!/^[0-9a-f]{64}$/.test(digest))
                throw new Error("PREVIEW_CONTENT_DIGEST_INVALID");
            if (asset.sha256 && asset.sha256 !== digest) {
                throw new Error("PREVIEW_CONTENT_DIGEST_MISMATCH");
            }
            if (!asset.sha256)
                update(asset.key, { sha256: digest });
            previewAssets.push({ ...asset, sha256: digest });
        }
        const previewScopeDigest = await sha256(new TextEncoder().encode(`preview-bootstrap\u0000${projectId}`).buffer);
        assertIntakeIdentityCurrent(identityGuard);
        await executeGuardedIntakeSkill(identityGuard, projectId, "elmos-multimodal-input-orchestrator", "bootstrap_project", {}, `mmi-preview-bootstrap-${previewScopeDigest.slice(0, 40)}`);
        const entries = previewAssets.map((asset) => ({
            path: asset.relativePath,
            kind: "file",
            byte_count: asset.file.size,
            content_digest: `sha256:${asset.sha256}`,
            role: asset.role,
            model_read_allowed: asset.modelReadAllowed && asset.phase === "READY",
            metadata: {
                ...(asset.assetId ? { asset_id: asset.assetId } : {}),
                intake_state: asset.phase,
            },
        }));
        const packageSessionId = `package-${crypto.randomUUID()}`;
        await executeGuardedIntakeSkill(identityGuard, projectId, "elmos-folder-tree-input", "begin", { session_id: packageSessionId, expected_entry_count: entries.length }, `mmi-package-begin-${packageSessionId}`);
        for (let offset = 0, chunkIndex = 0; offset < entries.length; offset += 1_000, chunkIndex += 1) {
            await executeGuardedIntakeSkill(identityGuard, projectId, "elmos-folder-tree-input", "append", { session_id: packageSessionId, chunk_index: chunkIndex, entries: entries.slice(offset, offset + 1_000) }, `mmi-package-append-${packageSessionId}-${chunkIndex}`);
        }
        const finalized = await executeGuardedIntakeSkill(identityGuard, projectId, "elmos-folder-tree-input", "finalize", { session_id: packageSessionId }, `mmi-package-finalize-${packageSessionId}`);
        const packageVersion = nestedRecord(finalized).package_version;
        if (!Number.isSafeInteger(packageVersion) || Number(packageVersion) < 1) {
            throw new Error("PROJECT_PACKAGE_VERSION_INVALID");
        }
        const firstPage = await executeGuardedIntakeSkill(identityGuard, projectId, "elmos-project-package-preview-and-review-ui", "page", { package_version: packageVersion, limit: 100 }, `mmi-package-page-${packageSessionId}-0`);
        setPackagePreview(finalized);
        setPackagePage(projectPackagePage(firstPage));
        setPackagePageCursors([null]);
        setPackagePageIndex(0);
    }
    catch (error) {
        if (intakeIdentityIsCurrent(identityGuard)) {
            setFeedback(error instanceof Error ? error.message : "PACKAGE_PREVIEW_FAILED");
        }
    }
    finally {
        if (intakeBusyOwner.current === busyOwner)
            setBusy(false);
    }
      } catch (err) {
        console.warn("buildPackagePreview execution warning:", err);
      }
    },
    async loadPackagePage(cursor, targetIndex) {
      const fileInput = this.data.fileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = this.data.folderInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = this.data.fileAdditionLock || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = this.data.fileAdditionOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = this.data.selectionCapacity || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = this.data.recoveryByScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = this.data.recoveryLoad || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = this.data.reviewScopeGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = this.data.reviewRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = this.data.reviewEngineScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = this.data.recoveryIdentityGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = this.data.activeIdentityScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = this.data.intakeBusyOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = this.data.estimateRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = this.data.intakeProjectGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = this.data.activeProjectId || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        if (!packagePage || targetIndex < 0 || !safeProject(projectId))
        return;
    let identityGuard;
    try {
        identityGuard = captureIntakeIdentity();
    }
    catch (error) {
        setFeedback(error instanceof Error ? error.message : "MULTIMODAL_IDENTITY_SCOPE_UNAVAILABLE");
        return;
    }
    const busyOwner = intakeBusyOwner.current + 1;
    intakeBusyOwner.current = busyOwner;
    setBusy(true);
    setFeedback("");
    try {
        const response = await executeGuardedIntakeSkill(identityGuard, projectId, "elmos-project-package-preview-and-review-ui", "page", {
            package_version: packagePage.package_version,
            limit: 100,
            ...(cursor ? { cursor } : {}),
        }, `mmi-package-page-${packagePage.collection_digest}-${targetIndex}-${crypto.randomUUID()}`);
        const page = projectPackagePage(response);
        if (page.package_version !== packagePage.package_version
            || page.collection_digest !== packagePage.collection_digest)
            throw new Error("PROJECT_PACKAGE_PAGE_DRIFT");
        setPackagePage(page);
        setPackagePageIndex(targetIndex);
    }
    catch (error) {
        if (intakeIdentityIsCurrent(identityGuard)) {
            setFeedback(error instanceof Error ? error.message : "PROJECT_PACKAGE_PAGE_FAILED");
        }
    }
    finally {
        if (intakeBusyOwner.current === busyOwner)
            setBusy(false);
    }
      } catch (err) {
        console.warn("loadPackagePage execution warning:", err);
      }
    },
    selectedReviewTask() {
      const fileInput = this.data.fileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = this.data.folderInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = this.data.fileAdditionLock || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = this.data.fileAdditionOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = this.data.selectionCapacity || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = this.data.recoveryByScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = this.data.recoveryLoad || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = this.data.reviewScopeGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = this.data.reviewRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = this.data.reviewEngineScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = this.data.recoveryIdentityGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = this.data.activeIdentityScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = this.data.intakeBusyOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = this.data.estimateRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = this.data.intakeProjectGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = this.data.activeProjectId || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        return reviewTasks.find((task) => task.task_id === selectedReviewTaskId);
      } catch (err) {
        console.warn("selectedReviewTask execution warning:", err);
      }
    },
    beginReviewRequest() {
      const fileInput = this.data.fileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = this.data.folderInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = this.data.fileAdditionLock || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = this.data.fileAdditionOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = this.data.selectionCapacity || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = this.data.recoveryByScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = this.data.recoveryLoad || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = this.data.reviewScopeGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = this.data.reviewRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = this.data.reviewEngineScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = this.data.recoveryIdentityGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = this.data.activeIdentityScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = this.data.intakeBusyOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = this.data.estimateRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = this.data.intakeProjectGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = this.data.activeProjectId || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        const guard = {
        generation: reviewScopeGeneration.current,
        owner: reviewRequestOwner.current + 1,
        projectId,
        identityScope: reviewIdentityScope,
    };
    reviewRequestOwner.current = guard.owner;
    setReviewBusy(true);
    return guard;
      } catch (err) {
        console.warn("beginReviewRequest execution warning:", err);
      }
    },
    reviewRequestIsCurrent(guard) {
      const fileInput = this.data.fileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = this.data.folderInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = this.data.fileAdditionLock || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = this.data.fileAdditionOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = this.data.selectionCapacity || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = this.data.recoveryByScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = this.data.recoveryLoad || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = this.data.reviewScopeGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = this.data.reviewRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = this.data.reviewEngineScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = this.data.recoveryIdentityGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = this.data.activeIdentityScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = this.data.intakeBusyOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = this.data.estimateRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = this.data.intakeProjectGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = this.data.activeProjectId || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        return guard.generation === reviewScopeGeneration.current
        && guard.owner === reviewRequestOwner.current;
      } catch (err) {
        console.warn("reviewRequestIsCurrent execution warning:", err);
      }
    },
    assertReviewRequestCurrent(guard) {
      const fileInput = this.data.fileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = this.data.folderInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = this.data.fileAdditionLock || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = this.data.fileAdditionOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = this.data.selectionCapacity || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = this.data.recoveryByScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = this.data.recoveryLoad || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = this.data.reviewScopeGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = this.data.reviewRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = this.data.reviewEngineScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = this.data.recoveryIdentityGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = this.data.activeIdentityScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = this.data.intakeBusyOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = this.data.estimateRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = this.data.intakeProjectGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = this.data.activeProjectId || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        if (!reviewRequestIsCurrent(guard))
    throw new Error("HUMAN_REVIEW_SCOPE_CHANGED");
      } catch (err) {
        console.warn("assertReviewRequestCurrent execution warning:", err);
      }
    },
    finishReviewRequest(guard) {
      const fileInput = this.data.fileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = this.data.folderInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = this.data.fileAdditionLock || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = this.data.fileAdditionOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = this.data.selectionCapacity || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = this.data.recoveryByScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = this.data.recoveryLoad || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = this.data.reviewScopeGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = this.data.reviewRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = this.data.reviewEngineScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = this.data.recoveryIdentityGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = this.data.activeIdentityScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = this.data.intakeBusyOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = this.data.estimateRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = this.data.intakeProjectGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = this.data.activeProjectId || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        if (reviewRequestIsCurrent(guard))
    setReviewBusy(false);
      } catch (err) {
        console.warn("finishReviewRequest execution warning:", err);
      }
    },
    async executeGuardedReviewSkill(guard, skill, operation, input, idempotencyKey) {
      const fileInput = this.data.fileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = this.data.folderInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = this.data.fileAdditionLock || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = this.data.fileAdditionOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = this.data.selectionCapacity || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = this.data.recoveryByScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = this.data.recoveryLoad || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = this.data.reviewScopeGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = this.data.reviewRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = this.data.reviewEngineScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = this.data.recoveryIdentityGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = this.data.activeIdentityScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = this.data.intakeBusyOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = this.data.estimateRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = this.data.intakeProjectGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = this.data.activeProjectId || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        assertReviewRequestCurrent(guard);
    const response = await executeSkill(guard.projectId, skill, operation, input, idempotencyKey);
    assertReviewRequestCurrent(guard);
    return response;
      } catch (err) {
        console.warn("executeGuardedReviewSkill execution warning:", err);
      }
    },
    saveReviewClaim(claim) {
      const fileInput = this.data.fileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = this.data.folderInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = this.data.fileAdditionLock || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = this.data.fileAdditionOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = this.data.selectionCapacity || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = this.data.recoveryByScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = this.data.recoveryLoad || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = this.data.reviewScopeGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = this.data.reviewRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = this.data.reviewEngineScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = this.data.recoveryIdentityGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = this.data.activeIdentityScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = this.data.intakeBusyOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = this.data.estimateRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = this.data.intakeProjectGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = this.data.activeProjectId || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        if (!reviewIdentityScope || claim.identity_scope !== reviewIdentityScope)
        return false;
    const next = Object.fromEntries(Object.entries(reviewClaims).filter(([, value]) => (validReviewClaim(value, reviewIdentityScope))));
    next[claim.task_id] = claim;
    if (!persistReviewClaims(next, reviewIdentityScope))
        return false;
    setReviewClaims(next);
    return true;
      } catch (err) {
        console.warn("saveReviewClaim execution warning:", err);
      }
    },
    discardReviewClaim(taskId) {
      const fileInput = this.data.fileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = this.data.folderInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = this.data.fileAdditionLock || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = this.data.fileAdditionOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = this.data.selectionCapacity || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = this.data.recoveryByScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = this.data.recoveryLoad || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = this.data.reviewScopeGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = this.data.reviewRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = this.data.reviewEngineScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = this.data.recoveryIdentityGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = this.data.activeIdentityScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = this.data.intakeBusyOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = this.data.estimateRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = this.data.intakeProjectGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = this.data.activeProjectId || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        if (!reviewIdentityScope)
        return false;
    const next = Object.fromEntries(Object.entries(reviewClaims).filter(([candidateId, value]) => (candidateId !== taskId && validReviewClaim(value, reviewIdentityScope))));
    if (!persistReviewClaims(next, reviewIdentityScope))
        return false;
    setReviewClaims(next);
    return true;
      } catch (err) {
        console.warn("discardReviewClaim execution warning:", err);
      }
    },
    abandonReviewClaimRecovery(taskId) {
      const fileInput = this.data.fileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = this.data.folderInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = this.data.fileAdditionLock || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = this.data.fileAdditionOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = this.data.selectionCapacity || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = this.data.recoveryByScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = this.data.recoveryLoad || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = this.data.reviewScopeGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = this.data.reviewRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = this.data.reviewEngineScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = this.data.recoveryIdentityGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = this.data.activeIdentityScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = this.data.intakeBusyOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = this.data.estimateRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = this.data.intakeProjectGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = this.data.activeProjectId || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        if (!discardReviewClaim(taskId)) {
        setFeedback("HUMAN_REVIEW_CLAIM_RECOVERY_DISCARD_FAILED");
        return;
    }
    setReviewTasks((current) => current.filter((task) => task.task_id !== taskId));
    setSelectedReviewTaskId("");
    setFeedback("本地领取恢复已清除；请刷新队列后按最新任务版本重新领取。");
      } catch (err) {
        console.warn("abandonReviewClaimRecovery execution warning:", err);
      }
    },
    reconcileReviewClaims(tasks) {
      const fileInput = this.data.fileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = this.data.folderInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = this.data.fileAdditionLock || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = this.data.fileAdditionOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = this.data.selectionCapacity || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = this.data.recoveryByScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = this.data.recoveryLoad || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = this.data.reviewScopeGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = this.data.reviewRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = this.data.reviewEngineScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = this.data.recoveryIdentityGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = this.data.activeIdentityScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = this.data.intakeBusyOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = this.data.estimateRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = this.data.intakeProjectGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = this.data.activeProjectId || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        if (!reviewIdentityScope)
        return;
    const next = { ...reviewClaims };
    let changed = false;
    for (const [taskId, claim] of Object.entries(next)) {
        if (!validReviewClaim(claim, reviewIdentityScope)) {
            delete next[taskId];
            changed = true;
            continue;
        }
        if (claim.project_id !== projectId)
            continue;
        const task = tasks.find((candidate) => candidate.task_id === taskId);
        const closed = task && ["APPROVED", "REJECTED", "REVERTING", "REVERTED"].includes(task.state);
        const fencedDrift = task && claim.fence !== undefined && (task.claim_fence !== claim.fence
            || task.claim_expires_at !== claim.expires_at
            || !["CLAIMED", "EDITED"].includes(task.state));
        // A pending receipt is the only durable handle for replaying a claim
        // whose response was lost.  List state is observational: CLAIMED vN+1
        // can mean this exact request committed.  Preserve the original key and
        // token until the server gives a definitive conflict or the bounded
        // recovery window expires.
        if (!task || closed || fencedDrift) {
            delete next[taskId];
            changed = true;
        }
    }
    if (changed && persistReviewClaims(next, reviewIdentityScope)) {
        setReviewClaims(next);
    }
      } catch (err) {
        console.warn("reconcileReviewClaims execution warning:", err);
      }
    },
    async validatedReviewTask(response, guard, expected) {
      const fileInput = this.data.fileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = this.data.folderInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = this.data.fileAdditionLock || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = this.data.fileAdditionOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = this.data.selectionCapacity || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = this.data.recoveryByScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = this.data.recoveryLoad || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = this.data.reviewScopeGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = this.data.reviewRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = this.data.reviewEngineScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = this.data.recoveryIdentityGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = this.data.activeIdentityScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = this.data.intakeBusyOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = this.data.estimateRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = this.data.intakeProjectGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = this.data.activeProjectId || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        assertReviewRequestCurrent(guard);
    const task = reviewTask(outputRecord(response, "task"), reviewEngineScope.current);
    if (!task)
        throw new Error("HUMAN_REVIEW_TASK_RESPONSE_INVALID");
    if (expected.priorTask) {
        const immutable = (candidate) => ({
            tenant_id: candidate.tenant_id,
            project_id: candidate.project_id,
            created_by: candidate.created_by,
            asset_id: candidate.asset_id,
            target_kind: candidate.target_kind,
            target: candidate.target,
            original_value: candidate.original_value,
            source_digest: candidate.source_digest,
            source_ref: candidate.source_ref,
            confidence: candidate.confidence,
            reason: candidate.reason,
            created_at: candidate.created_at,
        });
        if (!expected.priorTask.detail_loaded
            || !task.detail_loaded
            || canonicalStrictJson(immutable(task))
                !== canonicalStrictJson(immutable(expected.priorTask))
            || task.version < expected.priorTask.version
            || task.version === expected.priorTask.version
                && canonicalStrictJson(reviewTaskDynamicState(task))
                    !== canonicalStrictJson(reviewTaskDynamicState(expected.priorTask)))
            throw new Error("HUMAN_REVIEW_TASK_IMMUTABLE_BINDING_INVALID");
    }
    if (expected.taskId !== undefined && task.task_id !== expected.taskId
        || expected.assetId !== undefined && task.asset_id !== expected.assetId
        || expected.targetKind !== undefined && task.target_kind !== expected.targetKind
        || expected.target !== undefined && (task.target === undefined
            || canonicalStrictJson(task.target) !== canonicalStrictJson(expected.target))
        || expected.bindOriginalValue === true && (!Object.hasOwn(task, "original_value")
            || canonicalStrictJson(task.original_value) !== canonicalStrictJson(expected.originalValue))
        || expected.state !== undefined && task.state !== expected.state
        || expected.version !== undefined && task.version !== expected.version
        || expected.minimumVersion !== undefined && task.version < expected.minimumVersion
        || expected.correctionVersion !== undefined
            && task.current_correction_version !== expected.correctionVersion
        || expected.claimFence !== undefined && task.claim_fence !== expected.claimFence) {
        throw new Error("HUMAN_REVIEW_TASK_RESPONSE_BINDING_INVALID");
    }
    if (task.detail_loaded) {
        const expectedClientDigest = task.source_ref?.original_value_client_digest;
        const observedClientDigest = `sha256:${await sha256(new TextEncoder().encode(canonicalStrictJson(task.original_value)).buffer)}`;
        if (observedClientDigest !== expectedClientDigest) {
            throw new Error("HUMAN_REVIEW_ORIGINAL_VALUE_DIGEST_INVALID");
        }
    }
    assertReviewRequestCurrent(guard);
    return task;
      } catch (err) {
        console.warn("validatedReviewTask execution warning:", err);
      }
    },
    commitReviewTask(task) {
      const fileInput = this.data.fileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = this.data.folderInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = this.data.fileAdditionLock || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = this.data.fileAdditionOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = this.data.selectionCapacity || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = this.data.recoveryByScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = this.data.recoveryLoad || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = this.data.reviewScopeGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = this.data.reviewRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = this.data.reviewEngineScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = this.data.recoveryIdentityGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = this.data.activeIdentityScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = this.data.intakeBusyOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = this.data.estimateRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = this.data.intakeProjectGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = this.data.activeProjectId || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        setReviewTasks((current) => [
        task,
        ...current.filter((candidate) => candidate.task_id !== task.task_id),
    ].sort((left, right) => left.confidence - right.confidence || left.task_id.localeCompare(right.task_id)));
    setSelectedReviewTaskId(task.task_id);
    return task;
      } catch (err) {
        console.warn("commitReviewTask execution warning:", err);
      }
    },
    async ensureReviewProject(guard) {
      const fileInput = this.data.fileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = this.data.folderInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = this.data.fileAdditionLock || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = this.data.fileAdditionOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = this.data.selectionCapacity || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = this.data.recoveryByScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = this.data.recoveryLoad || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = this.data.reviewScopeGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = this.data.reviewRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = this.data.reviewEngineScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = this.data.recoveryIdentityGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = this.data.activeIdentityScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = this.data.intakeBusyOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = this.data.estimateRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = this.data.intakeProjectGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = this.data.activeProjectId || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        if (!safeProject(guard.projectId))
        throw new Error("PROJECT_ID_INVALID");
    const scopeDigest = await sha256(new TextEncoder().encode(`review-bootstrap\u0000${guard.projectId}`).buffer);
    assertReviewRequestCurrent(guard);
    const response = await executeGuardedReviewSkill(guard, "elmos-multimodal-input-orchestrator", "bootstrap_project", {}, `mmi-review-bootstrap-${scopeDigest.slice(0, 40)}`);
    const tenantId = responseString(response, "tenant_id");
    const engineProjectId = responseString(response, "project_id", "engine_project_id");
    if (!boundedOpaque(tenantId) || !boundedOpaque(engineProjectId)) {
        throw new Error("HUMAN_REVIEW_ENGINE_SCOPE_MISSING");
    }
    const prior = reviewEngineScope.current;
    if (prior && (prior.tenantId !== tenantId || prior.projectId !== engineProjectId)) {
        throw new Error("HUMAN_REVIEW_ENGINE_SCOPE_CHANGED");
    }
    assertReviewRequestCurrent(guard);
    reviewEngineScope.current = { tenantId, projectId: engineProjectId };
      } catch (err) {
        console.warn("ensureReviewProject execution warning:", err);
      }
    },
    async refreshReviewQueue() {
      const fileInput = this.data.fileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = this.data.folderInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = this.data.fileAdditionLock || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = this.data.fileAdditionOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = this.data.selectionCapacity || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = this.data.recoveryByScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = this.data.recoveryLoad || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = this.data.reviewScopeGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = this.data.reviewRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = this.data.reviewEngineScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = this.data.recoveryIdentityGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = this.data.activeIdentityScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = this.data.intakeBusyOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = this.data.estimateRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = this.data.intakeProjectGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = this.data.activeProjectId || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        const guard = beginReviewRequest();
    setFeedback("");
    setReviewPropagation(null);
    try {
        await ensureReviewProject(guard);
        const engineScope = reviewEngineScope.current;
        if (!engineScope)
            throw new Error("HUMAN_REVIEW_ENGINE_SCOPE_MISSING");
        const cursorFilterDigest = await sha256(new TextEncoder().encode(canonicalStrictJson({
            tenant_id: engineScope.tenantId,
            project_id: engineScope.projectId,
            kinds: [],
            states: [],
            confidence_lte: 1,
        })).buffer);
        assertReviewRequestCurrent(guard);
        const tasks = [];
        const taskIds = new Set();
        const cursors = new Set();
        let cursor = null;
        let expectedTotal;
        let pageCount = 0;
        do {
            pageCount += 1;
            if (pageCount > maximumReviewQueuePages) {
                throw new Error("HUMAN_REVIEW_TASK_PAGE_LIMIT_EXCEEDED");
            }
            const response = await executeGuardedReviewSkill(guard, "elmos-human-review-and-correction", "list", {
                kinds: [],
                states: [],
                confidence_lte: 1,
                limit: 200,
                cursor,
            }, `mmi-review-list-${crypto.randomUUID()}`);
            const output = exactReviewOutput(response, ["tasks", "next_cursor", "total"]);
            const rawTasks = output.tasks;
            const total = output.total;
            const nextCursor = output.next_cursor;
            if (!Array.isArray(rawTasks)
                || rawTasks.length > 200
                || typeof total !== "number"
                || !Number.isSafeInteger(total)
                || total < 0
                || total > maximumReviewQueueTasks
                || (nextCursor !== null && (typeof nextCursor !== "string" || !boundedOpaque(nextCursor)))
                || (expectedTotal !== undefined && total !== expectedTotal))
                throw new Error("HUMAN_REVIEW_TASK_LIST_INVALID");
            expectedTotal = total;
            for (const value of rawTasks) {
                const task = reviewTask(value);
                if (!task || taskIds.has(task.task_id)) {
                    throw new Error("HUMAN_REVIEW_TASK_LIST_INVALID");
                }
                taskIds.add(task.task_id);
                tasks.push(task);
            }
            if (tasks.length > total || tasks.length > maximumReviewQueueTasks) {
                throw new Error("HUMAN_REVIEW_TASK_LIST_INVALID");
            }
            if (nextCursor !== null) {
                const lastTask = tasks.at(-1);
                if (cursors.has(nextCursor)
                    || rawTasks.length !== 200
                    || tasks.length >= total
                    || pageCount >= Math.ceil(total / 200)
                    || !lastTask
                    || !exactReviewCursor(nextCursor, cursorFilterDigest, lastTask)) {
                    throw new Error("HUMAN_REVIEW_TASK_CURSOR_INVALID");
                }
                cursors.add(nextCursor);
            }
            cursor = nextCursor;
        } while (cursor !== null);
        if (tasks.length !== expectedTotal) {
            throw new Error("HUMAN_REVIEW_TASK_LIST_CHANGED");
        }
        setReviewTasks(tasks);
        reconcileReviewClaims(tasks);
        setSelectedReviewTaskId("");
        setCorrection("");
        setCorrectionTouched(false);
        setReviewPropagation(null);
        setReviewCurrentCorrection(null);
        setFeedback(`已完整载入 ${tasks.length} 个审阅任务；低置信项优先。`);
    }
    catch (error) {
        if (reviewRequestIsCurrent(guard)) {
            setFeedback(error instanceof Error ? error.message : "HUMAN_REVIEW_LIST_FAILED");
        }
    }
    finally {
        finishReviewRequest(guard);
    }
      } catch (err) {
        console.warn("refreshReviewQueue execution warning:", err);
      }
    },
    async fetchCurrentReviewCorrection(guard, task) {
      const fileInput = this.data.fileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = this.data.folderInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = this.data.fileAdditionLock || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = this.data.fileAdditionOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = this.data.selectionCapacity || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = this.data.recoveryByScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = this.data.recoveryLoad || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = this.data.reviewScopeGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = this.data.reviewRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = this.data.reviewEngineScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = this.data.recoveryIdentityGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = this.data.activeIdentityScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = this.data.intakeBusyOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = this.data.estimateRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = this.data.intakeProjectGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = this.data.activeProjectId || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        if (task.current_correction_version === 0)
        return undefined;
    const response = await executeGuardedReviewSkill(guard, "elmos-human-review-and-correction", "current_correction", { task_id: task.task_id }, `mmi-review-current-correction-${task.task_id}-${task.current_correction_version}`);
    const output = exactReviewOutput(response, ["correction"]);
    if (!exactCurrentReviewCorrection(output.correction, task)) {
        throw new Error("HUMAN_REVIEW_CURRENT_CORRECTION_RESPONSE_INVALID");
    }
    assertReviewRequestCurrent(guard);
    return output.correction;
      } catch (err) {
        console.warn("fetchCurrentReviewCorrection execution warning:", err);
      }
    },
    async selectReviewTask(taskId) {
      const fileInput = this.data.fileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = this.data.folderInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = this.data.fileAdditionLock || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = this.data.fileAdditionOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = this.data.selectionCapacity || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = this.data.recoveryByScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = this.data.recoveryLoad || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = this.data.reviewScopeGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = this.data.reviewRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = this.data.reviewEngineScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = this.data.recoveryIdentityGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = this.data.activeIdentityScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = this.data.intakeBusyOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = this.data.estimateRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = this.data.intakeProjectGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = this.data.activeProjectId || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        if (taskId !== selectedReviewTaskId) {
        setCorrection("");
        setCorrectionTouched(false);
        setReviewCurrentCorrection(null);
    }
    setSelectedReviewTaskId(taskId);
    setReviewPropagation(null);
    const summary = reviewTasks.find((task) => task.task_id === taskId);
    if (!summary)
        return;
    const guard = beginReviewRequest();
    setFeedback("");
    try {
        let detail = summary;
        if (!summary.detail_loaded) {
            const response = await executeGuardedReviewSkill(guard, "elmos-human-review-and-correction", "get", { task_id: taskId }, `mmi-review-get-${taskId}-${summary.version}`);
            exactReviewOutput(response, ["task"]);
            detail = await validatedReviewTask(response, guard, {
                taskId,
                assetId: summary.asset_id,
                targetKind: summary.target_kind,
                minimumVersion: summary.version,
            });
            assertReviewRequestCurrent(guard);
            const immutableSummary = {
                asset_id: summary.asset_id,
                target_kind: summary.target_kind,
                source_digest: summary.source_digest,
                confidence: summary.confidence,
                reason: summary.reason,
                created_at: summary.created_at,
            };
            const immutableDetail = {
                asset_id: detail.asset_id,
                target_kind: detail.target_kind,
                source_digest: detail.source_digest,
                confidence: detail.confidence,
                reason: detail.reason,
                created_at: detail.created_at,
            };
            if (!detail.detail_loaded
                || canonicalStrictJson(immutableSummary) !== canonicalStrictJson(immutableDetail)
                || detail.version === summary.version
                    && canonicalStrictJson(reviewTaskDynamicState(summary))
                        !== canonicalStrictJson(reviewTaskDynamicState(detail)))
                throw new Error("HUMAN_REVIEW_TASK_DETAIL_INVALID");
        }
        const currentCorrection = await fetchCurrentReviewCorrection(guard, detail);
        assertReviewRequestCurrent(guard);
        commitReviewTask(detail);
        setReviewCurrentCorrection(currentCorrection ?? null);
        setFeedback(currentCorrection
            ? `审阅任务 ${taskId} 的权威原值、来源与当前纠正版本已载入。`
            : `审阅任务 ${taskId} 的权威原值与来源已载入。`);
    }
    catch (error) {
        if (reviewRequestIsCurrent(guard)) {
            setSelectedReviewTaskId("");
            setFeedback(error instanceof Error ? error.message : "HUMAN_REVIEW_TASK_DETAIL_FAILED");
        }
    }
    finally {
        finishReviewRequest(guard);
    }
      } catch (err) {
        console.warn("selectReviewTask execution warning:", err);
      }
    },
    async refreshReviewSources() {
      const fileInput = this.data.fileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = this.data.folderInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = this.data.fileAdditionLock || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = this.data.fileAdditionOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = this.data.selectionCapacity || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = this.data.recoveryByScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = this.data.recoveryLoad || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = this.data.reviewScopeGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = this.data.reviewRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = this.data.reviewEngineScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = this.data.recoveryIdentityGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = this.data.activeIdentityScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = this.data.intakeBusyOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = this.data.estimateRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = this.data.intakeProjectGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = this.data.activeProjectId || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        const asset = assets.find((candidate) => candidate.assetId === correctionTarget);
    if (!asset?.assetId || !asset.sha256 || !positiveInteger(asset.assetVersion)) {
        setFeedback("HUMAN_REVIEW_SOURCE_ASSET_REQUIRED");
        return;
    }
    const guard = beginReviewRequest();
    setFeedback("");
    try {
        await ensureReviewProject(guard);
        const engineScope = reviewEngineScope.current;
        if (!engineScope)
            throw new Error("HUMAN_REVIEW_ENGINE_SCOPE_MISSING");
        const filterDigest = await sha256(new TextEncoder().encode(canonicalStrictJson({
            schema_version: "human-review-source-filter-v1",
            tenant_id: engineScope.tenantId,
            project_id: engineScope.projectId,
            content_id: asset.assetId,
            content_version: asset.assetVersion,
            kinds: [],
        })).buffer);
        assertReviewRequestCurrent(guard);
        const sources = [];
        const sourceKeys = new Set();
        const cursors = new Set();
        let cursor = null;
        let collectionDigest;
        let collectionGeneration;
        let expectedTotal;
        let pageCount = 0;
        do {
            pageCount += 1;
            if (pageCount > maximumReviewSourcePages) {
                throw new Error("HUMAN_REVIEW_SOURCE_PAGE_LIMIT_EXCEEDED");
            }
            const response = await executeGuardedReviewSkill(guard, "elmos-human-review-and-correction", "source_list", {
                content_id: asset.assetId,
                expected_asset_version: asset.assetVersion,
                kinds: [],
                limit: 200,
                cursor,
            }, `mmi-review-source-list-${crypto.randomUUID()}`);
            const output = exactReviewOutput(response, ["sources", "next_cursor", "total"]);
            const rawSources = output.sources;
            const total = output.total;
            const nextCursor = output.next_cursor;
            if (!Array.isArray(rawSources)
                || rawSources.length > 200
                || typeof total !== "number"
                || !Number.isSafeInteger(total)
                || total < 0
                || total > maximumReviewSources
                || !(nextCursor === null || typeof nextCursor === "string")
                || expectedTotal !== undefined && total !== expectedTotal)
                throw new Error("HUMAN_REVIEW_SOURCE_LIST_INVALID");
            expectedTotal = total;
            for (const value of rawSources) {
                const source = reviewSource(value);
                if (!source
                    || source.detail_loaded
                    || source.content_id !== asset.assetId
                    || source.content_version !== asset.assetVersion
                    || source.source_ref.asset_sha256 !== `sha256:${asset.sha256}`)
                    throw new Error("HUMAN_REVIEW_SOURCE_LIST_INVALID");
                const key = reviewSourceKey(source);
                if (sourceKeys.has(key))
                    throw new Error("HUMAN_REVIEW_SOURCE_LIST_INVALID");
                sourceKeys.add(key);
                sources.push(source);
            }
            if (sources.length > total || sources.length > maximumReviewSources) {
                throw new Error("HUMAN_REVIEW_SOURCE_LIST_INVALID");
            }
            if (nextCursor !== null) {
                const lastSource = sources.at(-1);
                const observedCursorBinding = lastSource
                    ? exactReviewSourceCursor(nextCursor, filterDigest, collectionDigest, collectionGeneration, lastSource)
                    : undefined;
                if (cursors.has(nextCursor)
                    || rawSources.length !== 200
                    || sources.length >= total
                    || pageCount >= Math.ceil(total / 200)
                    || observedCursorBinding === undefined)
                    throw new Error("HUMAN_REVIEW_SOURCE_CURSOR_INVALID");
                collectionDigest = observedCursorBinding.collectionDigest;
                collectionGeneration = observedCursorBinding.collectionGeneration;
                cursors.add(nextCursor);
            }
            cursor = nextCursor;
        } while (cursor !== null);
        if (sources.length !== expectedTotal) {
            throw new Error("HUMAN_REVIEW_SOURCE_COLLECTION_CHANGED");
        }
        assertReviewRequestCurrent(guard);
        setReviewSources([...sources].sort((left, right) => (left.confidence - right.confidence
            || left.target_kind.localeCompare(right.target_kind)
            || left.target_digest.localeCompare(right.target_digest))));
        setSelectedReviewSourceKey("");
        setReviewTargetLocator("");
        setReviewOriginalValue("");
        setFeedback(`已载入 ${sources.length} 个版本绑定的权威待审来源；请选择一项查看原值。`);
    }
    catch (error) {
        if (reviewRequestIsCurrent(guard)) {
            setFeedback(error instanceof Error ? error.message : "HUMAN_REVIEW_SOURCE_LIST_FAILED");
        }
    }
    finally {
        finishReviewRequest(guard);
    }
      } catch (err) {
        console.warn("refreshReviewSources execution warning:", err);
      }
    },
    async selectReviewSource(key) {
      const fileInput = this.data.fileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = this.data.folderInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = this.data.fileAdditionLock || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = this.data.fileAdditionOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = this.data.selectionCapacity || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = this.data.recoveryByScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = this.data.recoveryLoad || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = this.data.reviewScopeGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = this.data.reviewRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = this.data.reviewEngineScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = this.data.recoveryIdentityGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = this.data.activeIdentityScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = this.data.intakeBusyOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = this.data.estimateRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = this.data.intakeProjectGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = this.data.activeProjectId || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        setSelectedReviewSourceKey(key);
    setReviewTargetLocator("");
    setReviewOriginalValue("");
    const summary = reviewSources.find((source) => reviewSourceKey(source) === key);
    const asset = assets.find((candidate) => candidate.assetId === correctionTarget);
    if (!summary || !asset?.assetId || !asset.sha256 || !positiveInteger(asset.assetVersion))
        return;
    const guard = beginReviewRequest();
    setFeedback("");
    try {
        const response = await executeGuardedReviewSkill(guard, "elmos-human-review-and-correction", "source_get", {
            content_id: summary.content_id,
            expected_asset_version: summary.content_version,
            target_kind: summary.target_kind,
            target_digest: summary.target_digest,
            expected_head_version: summary.head_version,
        }, `mmi-review-source-get-${crypto.randomUUID()}`);
        const output = exactReviewOutput(response, ["source"]);
        const detail = await validatedReviewSource(output.source, {
            contentId: asset.assetId,
            contentVersion: summary.content_version,
            priorSummary: summary,
        });
        assertReviewRequestCurrent(guard);
        if (detail.source_ref.asset_sha256 !== `sha256:${asset.sha256}`) {
            throw new Error("HUMAN_REVIEW_SOURCE_ASSET_DIGEST_INVALID");
        }
        setReviewSources((current) => [
            detail,
            ...current.filter((source) => reviewSourceKey(source) !== key),
        ].sort((left, right) => (left.confidence - right.confidence
            || left.target_kind.localeCompare(right.target_kind)
            || left.target_digest.localeCompare(right.target_digest))));
        setReviewTargetKind(detail.target_kind);
        setReviewTargetLocator(canonicalStrictJson(detail.target));
        setReviewOriginalValue(detail.target_kind === "TEXT" && typeof detail.original_value === "string"
            ? detail.original_value
            : canonicalStrictJson(detail.original_value));
        setReviewConfidence(String(detail.confidence));
        setFeedback("权威来源详情已载入并绑定当前 asset/snapshot/head；现在可创建审阅任务。");
    }
    catch (error) {
        if (reviewRequestIsCurrent(guard)) {
            setSelectedReviewSourceKey("");
            setFeedback(error instanceof Error ? error.message : "HUMAN_REVIEW_SOURCE_GET_FAILED");
        }
    }
    finally {
        finishReviewRequest(guard);
    }
      } catch (err) {
        console.warn("selectReviewSource execution warning:", err);
      }
    },
    async validatedReviewEnqueueReceipt(response, guard, input, outputKeys) {
      const fileInput = this.data.fileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = this.data.folderInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = this.data.fileAdditionLock || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = this.data.fileAdditionOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = this.data.selectionCapacity || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = this.data.recoveryByScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = this.data.recoveryLoad || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = this.data.reviewScopeGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = this.data.reviewRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = this.data.reviewEngineScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = this.data.recoveryIdentityGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = this.data.activeIdentityScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = this.data.intakeBusyOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = this.data.estimateRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = this.data.intakeProjectGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = this.data.activeProjectId || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        exactReviewOutput(response, outputKeys);
    const task = await validatedReviewTask(response, guard, {
        assetId: input.content_id,
        targetKind: input.target_kind,
        state: "QUEUED",
        version: 1,
        correctionVersion: 0,
    });
    assertReviewRequestCurrent(guard);
    const sourceRef = task.source_ref;
    if (!task.detail_loaded
        || !sourceRef
        || task.reason !== input.reason
        || task.source_digest !== input.expected_head_value_digest
        || sourceRef.content_version !== input.expected_asset_version
        || sourceRef.target_digest !== input.target_digest
        || sourceRef.head_version !== input.expected_head_version
        || sourceRef.snapshot_id !== input.expected_snapshot_id
        || sourceRef.snapshot_digest !== input.expected_snapshot_digest
        || sourceRef.head_value_digest !== input.expected_head_value_digest
        || sourceRef.original_value_client_digest !== input.original_value_digest
        || sourceRef.original_value_digest_contract
            !== "sha256:rfc8785-ijson-safeint-v1")
        throw new Error("HUMAN_REVIEW_ENQUEUE_RECEIPT_BINDING_INVALID");
    return task;
      } catch (err) {
        console.warn("validatedReviewEnqueueReceipt execution warning:", err);
      }
    },
    clearReviewEnqueueAttempt(guard, attempt) {
      const fileInput = this.data.fileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = this.data.folderInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = this.data.fileAdditionLock || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = this.data.fileAdditionOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = this.data.selectionCapacity || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = this.data.recoveryByScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = this.data.recoveryLoad || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = this.data.reviewScopeGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = this.data.reviewRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = this.data.reviewEngineScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = this.data.recoveryIdentityGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = this.data.activeIdentityScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = this.data.intakeBusyOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = this.data.estimateRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = this.data.intakeProjectGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = this.data.activeProjectId || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        assertReviewRequestCurrent(guard);
    const attempts = loadReviewEnqueueAttempts(guard.identityScope);
    const persisted = attempts[attempt.request_digest];
    if (!persisted
        || canonicalStrictJson(persisted) !== canonicalStrictJson(attempt))
        throw new Error("HUMAN_REVIEW_ENQUEUE_RECOVERY_BINDING_INVALID");
    delete attempts[attempt.request_digest];
    if (!persistReviewEnqueueAttempts(guard.identityScope, attempts)) {
        throw new Error("HUMAN_REVIEW_ENQUEUE_RECOVERY_CLEAR_FAILED");
    }
    setReviewEnqueueRecoveryCount(Object.values(attempts).filter((candidate) => candidate.project_scope_digest === attempt.project_scope_digest).length);
    setReviewEnqueueRecoveryError("");
      } catch (err) {
        console.warn("clearReviewEnqueueAttempt execution warning:", err);
      }
    },
    async recoverReviewEnqueueAttempts() {
      const fileInput = this.data.fileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = this.data.folderInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = this.data.fileAdditionLock || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = this.data.fileAdditionOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = this.data.selectionCapacity || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = this.data.recoveryByScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = this.data.recoveryLoad || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = this.data.reviewScopeGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = this.data.reviewRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = this.data.reviewEngineScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = this.data.recoveryIdentityGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = this.data.activeIdentityScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = this.data.intakeBusyOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = this.data.estimateRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = this.data.intakeProjectGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = this.data.activeProjectId || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        if (!reviewIdentityScope) {
        setFeedback("HUMAN_REVIEW_IDENTITY_SCOPE_UNAVAILABLE");
        return;
    }
    const guard = beginReviewRequest();
    setFeedback("");
    let recovered = 0;
    let safelyCleared = 0;
    try {
        await ensureReviewProject(guard);
        const projectScopeDigest = await reviewProjectScopeDigest(guard.identityScope, guard.projectId);
        assertReviewRequestCurrent(guard);
        const storedAttempts = loadReviewEnqueueAttempts(guard.identityScope);
        const attempts = Object.values(storedAttempts).filter((attempt) => attempt.project_scope_digest === projectScopeDigest).sort((left, right) => (left.created_at - right.created_at
            || left.request_digest.localeCompare(right.request_digest)));
        if (attempts.length === 0) {
            setReviewEnqueueRecoveryCount(0);
            setReviewEnqueueRecoveryError("");
            setFeedback("当前项目没有待恢复的审阅入队请求。");
            return;
        }
        for (const attempt of attempts) {
            assertReviewRequestCurrent(guard);
            if (attempt.project_scope_digest !== projectScopeDigest) {
                throw new Error("HUMAN_REVIEW_ENQUEUE_RECOVERY_BINDING_INVALID");
            }
            const response = await executeGuardedReviewSkill(guard, "elmos-human-review-and-correction", "enqueue_execute", { recovery_handle: attempt.recovery_handle }, attempt.execute_idempotency_key);
            if (response.code === "HUMAN_REVIEW_ENQUEUE_PREPARATION_ABSENT") {
                const output = exactReviewOutput(response, ["preparation"]);
                if (!exactReviewEnqueuePreparationAbsence(output.preparation, attempt)) {
                    throw new Error("HUMAN_REVIEW_ENQUEUE_PREPARATION_INVALID");
                }
                clearReviewEnqueueAttempt(guard, attempt);
                safelyCleared += 1;
                continue;
            }
            if (response.code === "HUMAN_REVIEW_ENQUEUE_PREPARATION_EXPIRED") {
                const output = exactReviewOutput(response, ["preparation"]);
                await validatedReviewEnqueuePreparation(output.preparation, attempt, new Set(["EXPIRED"]));
                assertReviewRequestCurrent(guard);
                clearReviewEnqueueAttempt(guard, attempt);
                safelyCleared += 1;
                continue;
            }
            if (response.code !== "HUMAN_REVIEW_TASK_ENQUEUED_FROM_PREPARATION") {
                throw new Error("HUMAN_REVIEW_ENQUEUE_EXECUTE_RESPONSE_INVALID");
            }
            const output = exactReviewOutput(response, ["preparation", "task"]);
            const { preparation, input } = await validatedReviewEnqueuePreparation(output.preparation, attempt, new Set(["EXECUTED"]));
            assertReviewRequestCurrent(guard);
            const receiptTask = await validatedReviewEnqueueReceipt(response, guard, input, ["preparation", "task"]);
            if (preparation.task_id !== receiptTask.task_id) {
                throw new Error("HUMAN_REVIEW_ENQUEUE_RECEIPT_BINDING_INVALID");
            }
            clearReviewEnqueueAttempt(guard, attempt);
            const currentResponse = await executeGuardedReviewSkill(guard, "elmos-human-review-and-correction", "get", { task_id: receiptTask.task_id }, `mmi-review-get-${receiptTask.task_id}-${receiptTask.version}-${crypto.randomUUID()}`);
            exactReviewOutput(currentResponse, ["task"]);
            const currentTask = await validatedReviewTask(currentResponse, guard, {
                priorTask: receiptTask,
                taskId: receiptTask.task_id,
                assetId: input.content_id,
                targetKind: input.target_kind,
                minimumVersion: receiptTask.version,
            });
            commitReviewTask(currentTask);
            recovered += 1;
        }
        setFeedback(`审阅入队恢复完成：${recovered} 个已提交任务载入权威当前状态，${safelyCleared} 个明确未执行或已过期句柄已清理。`);
    }
    catch (error) {
        if (reviewRequestIsCurrent(guard)) {
            await updateReviewEnqueueRecoveryState(guard.identityScope, guard.projectId);
            setFeedback(error instanceof Error
                ? error.message
                : "HUMAN_REVIEW_ENQUEUE_RECOVERY_FAILED");
        }
    }
    finally {
        finishReviewRequest(guard);
    }
      } catch (err) {
        console.warn("recoverReviewEnqueueAttempts execution warning:", err);
      }
    },
    async enqueueReviewTask() {
      const fileInput = this.data.fileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = this.data.folderInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = this.data.fileAdditionLock || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = this.data.fileAdditionOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = this.data.selectionCapacity || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = this.data.recoveryByScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = this.data.recoveryLoad || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = this.data.reviewScopeGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = this.data.reviewRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = this.data.reviewEngineScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = this.data.recoveryIdentityGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = this.data.activeIdentityScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = this.data.intakeBusyOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = this.data.estimateRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = this.data.intakeProjectGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = this.data.activeProjectId || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        const asset = assets.find((candidate) => candidate.assetId === correctionTarget);
    const selectedSource = reviewSources.find((source) => (reviewSourceKey(source) === selectedReviewSourceKey && source.detail_loaded));
    const confidence = selectedSource?.confidence;
    const enqueueReason = reviewReason.trim();
    if (!reviewIdentityScope
        || !asset?.assetId
        || !asset.sha256
        || !positiveInteger(asset.assetVersion)
        || !selectedSource
        || selectedSource.content_id !== asset.assetId
        || selectedSource.content_version !== asset.assetVersion
        || selectedSource.source_ref.asset_sha256 !== `sha256:${asset.sha256}`
        || typeof confidence !== "number"
        || !Number.isFinite(confidence)
        || confidence < 0
        || confidence > 1
        || !exactRequiredText(enqueueReason, 2_000)) {
        setFeedback("HUMAN_REVIEW_ENQUEUE_INPUT_INVALID");
        return;
    }
    const guard = beginReviewRequest();
    setFeedback("");
    try {
        const target = selectedSource.target;
        const originalValue = selectedSource.original_value;
        const sourceRef = selectedSource.source_ref;
        await ensureReviewProject(guard);
        const originalValueClientDigest = `sha256:${await sha256(new TextEncoder().encode(canonicalStrictJson(originalValue)).buffer)}`;
        assertReviewRequestCurrent(guard);
        if (originalValueClientDigest !== selectedSource.original_value_client_digest
            || sourceRef.original_value_client_digest !== originalValueClientDigest)
            throw new Error("HUMAN_REVIEW_SOURCE_VALUE_DIGEST_INVALID");
        const enqueueInput = {
            content_id: asset.assetId,
            expected_asset_version: asset.assetVersion,
            target_kind: selectedSource.target_kind,
            target_digest: selectedSource.target_digest,
            original_value_digest: originalValueClientDigest,
            reason: enqueueReason,
            expected_head_version: selectedSource.head_version,
            expected_snapshot_id: sourceRef.snapshot_id,
            expected_snapshot_digest: sourceRef.snapshot_digest,
            expected_head_value_digest: sourceRef.head_value_digest,
        };
        const enqueueRequestDigest = await reviewEnqueueRequestDigest(enqueueInput);
        const projectScopeDigest = await reviewProjectScopeDigest(guard.identityScope, guard.projectId);
        assertReviewRequestCurrent(guard);
        const storedAttempts = loadReviewEnqueueAttempts(guard.identityScope);
        let enqueueAttempt = storedAttempts[enqueueRequestDigest];
        const recoveringUnknown = enqueueAttempt !== undefined;
        if (!enqueueAttempt) {
            if (Object.values(storedAttempts).some((attempt) => attempt.project_scope_digest === projectScopeDigest)) {
                throw new Error("HUMAN_REVIEW_ENQUEUE_RECOVERY_REQUIRED");
            }
            if (Object.keys(storedAttempts).length >= maximumStoredReviewEnqueueAttempts) {
                throw new Error("HUMAN_REVIEW_ENQUEUE_RECOVERY_LIMIT_EXCEEDED");
            }
            enqueueAttempt = {
                schema_version: 3,
                identity_scope: guard.identityScope,
                project_scope_digest: projectScopeDigest,
                request_digest: enqueueRequestDigest,
                recovery_handle: `mmi-review-recovery-${crypto.randomUUID()}`,
                prepare_idempotency_key: `mmi-review-enqueue-prepare-${crypto.randomUUID()}`,
                execute_idempotency_key: `mmi-review-enqueue-execute-${crypto.randomUUID()}`,
                created_at: Date.now(),
            };
            if (!persistReviewEnqueueAttempts(guard.identityScope, {
                ...storedAttempts,
                [enqueueRequestDigest]: enqueueAttempt,
            })) {
                throw new Error("HUMAN_REVIEW_ENQUEUE_RECOVERY_UNAVAILABLE");
            }
            setReviewEnqueueRecoveryCount(Object.values(storedAttempts).filter((attempt) => attempt.project_scope_digest === projectScopeDigest).length + 1);
            setReviewEnqueueRecoveryError("");
        }
        if (enqueueAttempt.project_scope_digest !== projectScopeDigest
            || enqueueAttempt.request_digest !== enqueueRequestDigest) {
            throw new Error("HUMAN_REVIEW_ENQUEUE_RECOVERY_BINDING_INVALID");
        }
        if (!recoveringUnknown) {
            const preparedResponse = await executeGuardedReviewSkill(guard, "elmos-human-review-and-correction", "enqueue_prepare", {
                recovery_handle: enqueueAttempt.recovery_handle,
                execute_idempotency_key: enqueueAttempt.execute_idempotency_key,
                ...enqueueInput,
            }, enqueueAttempt.prepare_idempotency_key);
            if (preparedResponse.code !== "HUMAN_REVIEW_ENQUEUE_PREPARED") {
                throw new Error("HUMAN_REVIEW_ENQUEUE_PREPARE_RESPONSE_INVALID");
            }
            const preparedOutput = exactReviewOutput(preparedResponse, ["preparation"]);
            const prepared = await validatedReviewEnqueuePreparation(preparedOutput.preparation, enqueueAttempt, new Set(["PREPARED"]));
            assertReviewRequestCurrent(guard);
            if (canonicalStrictJson(prepared.input) !== canonicalStrictJson(enqueueInput)) {
                throw new Error("HUMAN_REVIEW_ENQUEUE_PREPARATION_BINDING_INVALID");
            }
        }
        const response = await executeGuardedReviewSkill(guard, "elmos-human-review-and-correction", "enqueue_execute", { recovery_handle: enqueueAttempt.recovery_handle }, enqueueAttempt.execute_idempotency_key);
        if (response.code === "HUMAN_REVIEW_ENQUEUE_PREPARATION_ABSENT") {
            const output = exactReviewOutput(response, ["preparation"]);
            if (!exactReviewEnqueuePreparationAbsence(output.preparation, enqueueAttempt)) {
                throw new Error("HUMAN_REVIEW_ENQUEUE_PREPARATION_INVALID");
            }
            clearReviewEnqueueAttempt(guard, enqueueAttempt);
            throw new Error("HUMAN_REVIEW_ENQUEUE_PREPARATION_ABSENT_RETRY_REQUIRED");
        }
        if (response.code === "HUMAN_REVIEW_ENQUEUE_PREPARATION_EXPIRED") {
            const output = exactReviewOutput(response, ["preparation"]);
            await validatedReviewEnqueuePreparation(output.preparation, enqueueAttempt, new Set(["EXPIRED"]));
            assertReviewRequestCurrent(guard);
            clearReviewEnqueueAttempt(guard, enqueueAttempt);
            throw new Error("HUMAN_REVIEW_ENQUEUE_PREPARATION_EXPIRED_RETRY_REQUIRED");
        }
        if (response.code !== "HUMAN_REVIEW_TASK_ENQUEUED_FROM_PREPARATION") {
            throw new Error("HUMAN_REVIEW_ENQUEUE_EXECUTE_RESPONSE_INVALID");
        }
        const output = exactReviewOutput(response, ["preparation", "task"]);
        const executed = await validatedReviewEnqueuePreparation(output.preparation, enqueueAttempt, new Set(["EXECUTED"]));
        assertReviewRequestCurrent(guard);
        if (canonicalStrictJson(executed.input) !== canonicalStrictJson(enqueueInput)) {
            throw new Error("HUMAN_REVIEW_ENQUEUE_PREPARATION_BINDING_INVALID");
        }
        const receiptTask = await validatedReviewEnqueueReceipt(response, guard, executed.input, ["preparation", "task"]);
        if (executed.preparation.task_id !== receiptTask.task_id) {
            throw new Error("HUMAN_REVIEW_ENQUEUE_RECEIPT_BINDING_INVALID");
        }
        clearReviewEnqueueAttempt(guard, enqueueAttempt);
        assertReviewRequestCurrent(guard);
        if (!receiptTask.target
            || canonicalStrictJson(receiptTask.target) !== canonicalStrictJson(target)
            || canonicalStrictJson(receiptTask.original_value) !== canonicalStrictJson(originalValue)
            || receiptTask.confidence !== confidence
            || receiptTask.reason !== enqueueReason
            || receiptTask.source_ref?.content_version !== asset.assetVersion
            || receiptTask.source_ref?.asset_sha256 !== `sha256:${asset.sha256}`
            || receiptTask.source_ref?.original_value_client_digest !== originalValueClientDigest
            || receiptTask.source_ref?.original_value_digest_contract
                !== "sha256:rfc8785-ijson-safeint-v1"
            || receiptTask.source_digest !== sourceRef.head_value_digest
            || canonicalStrictJson(receiptTask.source_ref) !== canonicalStrictJson(sourceRef))
            throw new Error("HUMAN_REVIEW_SOURCE_RESPONSE_BINDING_INVALID");
        const currentResponse = await executeGuardedReviewSkill(guard, "elmos-human-review-and-correction", "get", { task_id: receiptTask.task_id }, `mmi-review-get-${receiptTask.task_id}-${receiptTask.version}`);
        exactReviewOutput(currentResponse, ["task"]);
        const currentTask = await validatedReviewTask(currentResponse, guard, {
            priorTask: receiptTask,
            taskId: receiptTask.task_id,
            assetId: asset.assetId,
            targetKind: selectedSource.target_kind,
            target,
            originalValue,
            bindOriginalValue: true,
            minimumVersion: receiptTask.version,
        });
        assertReviewRequestCurrent(guard);
        commitReviewTask(currentTask);
        setFeedback(recoveringUnknown
            ? `审阅任务 ${currentTask.task_id} 的未知结果已精确恢复；当前权威状态已载入。`
            : `审阅任务 ${currentTask.task_id} 已排队；原始资产保持不变。`);
    }
    catch (error) {
        if (reviewRequestIsCurrent(guard)) {
            await updateReviewEnqueueRecoveryState(guard.identityScope, guard.projectId);
            setFeedback(error instanceof Error ? error.message : "HUMAN_REVIEW_ENQUEUE_FAILED");
        }
    }
    finally {
        finishReviewRequest(guard);
    }
      } catch (err) {
        console.warn("enqueueReviewTask execution warning:", err);
      }
    },
    async claimReviewTask() {
      const fileInput = this.data.fileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = this.data.folderInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = this.data.fileAdditionLock || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = this.data.fileAdditionOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = this.data.selectionCapacity || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = this.data.recoveryByScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = this.data.recoveryLoad || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = this.data.reviewScopeGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = this.data.reviewRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = this.data.reviewEngineScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = this.data.recoveryIdentityGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = this.data.activeIdentityScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = this.data.intakeBusyOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = this.data.estimateRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = this.data.intakeProjectGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = this.data.activeProjectId || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        const task = selectedReviewTask();
    if (!task || !reviewIdentityScope) {
        setFeedback("HUMAN_REVIEW_IDENTITY_SCOPE_UNAVAILABLE");
        return;
    }
    const storedClaim = reviewClaims[task.task_id];
    const recoverable = storedClaim
        && storedClaim.project_id === projectId
        && validReviewClaim(storedClaim, reviewIdentityScope)
        ? storedClaim
        : undefined;
    if (storedClaim && !recoverable && !discardReviewClaim(task.task_id)) {
        setFeedback("HUMAN_REVIEW_CLAIM_RECOVERY_DISCARD_FAILED");
        return;
    }
    if (recoverable?.fence !== undefined && validReviewClaim(recoverable, reviewIdentityScope)) {
        setFeedback(`审阅任务 ${task.task_id} 的领取凭证仍有效。`);
        return;
    }
    const attempt = recoverable
        ? recoverable
        : {
            schema_version: 2,
            identity_scope: reviewIdentityScope,
            project_id: projectId,
            task_id: task.task_id,
            token: `review-claim:${crypto.randomUUID()}:${crypto.randomUUID()}`,
            idempotency_key: `mmi-review-claim-${task.task_id}-${crypto.randomUUID()}`,
            expected_version: task.version,
            created_at: Date.now(),
        };
    const guard = beginReviewRequest();
    if (!saveReviewClaim(attempt)) {
        setFeedback("HUMAN_REVIEW_CLAIM_RECOVERY_UNAVAILABLE");
        finishReviewRequest(guard);
        return;
    }
    setFeedback("");
    try {
        const response = await executeGuardedReviewSkill(guard, "elmos-human-review-and-correction", "claim", {
            task_id: task.task_id,
            expected_version: attempt.expected_version,
            claim_token: attempt.token,
            lease_seconds: reviewClaimLeaseSeconds,
        }, attempt.idempotency_key);
        exactReviewOutput(response, ["task"]);
        const observedCommittedReplay = recoverable?.fence === undefined
            && task.version === attempt.expected_version + 1
            && ["CLAIMED", "EDITED"].includes(task.state)
            && task.claim_fence !== undefined;
        const claimed = await validatedReviewTask(response, guard, {
            priorTask: task,
            taskId: task.task_id,
            assetId: task.asset_id,
            state: task.state === "EDITED" ? "EDITED" : "CLAIMED",
            version: attempt.expected_version + 1,
            correctionVersion: task.current_correction_version,
            claimFence: observedCommittedReplay
                ? task.claim_fence
                : (task.claim_fence ?? 0) + 1,
        });
        assertReviewRequestCurrent(guard);
        if (!claimed.claim_fence
            || !claimed.claim_expires_at
            || Date.parse(claimed.claim_expires_at) <= Date.now()
            || claimed.current_correction_digest !== task.current_correction_digest
            || claimed.effective_version !== task.effective_version
            || claimed.effective_digest !== task.effective_digest
            || observedCommittedReplay && claimed.claim_expires_at !== task.claim_expires_at
            || account.status === "authenticated"
                && claimed.claim_actor_id !== account.principal?.actorId) {
            throw new Error("HUMAN_REVIEW_CLAIM_FENCE_MISSING");
        }
        const completedClaim = {
            ...attempt,
            fence: claimed.claim_fence,
            expires_at: claimed.claim_expires_at,
        };
        if (!validReviewClaim(completedClaim, reviewIdentityScope) || !saveReviewClaim(completedClaim)) {
            throw new Error("HUMAN_REVIEW_CLAIM_RECOVERY_UNAVAILABLE");
        }
        assertReviewRequestCurrent(guard);
        commitReviewTask(claimed);
        setFeedback(`审阅任务 ${task.task_id} 已领取；租约写入持久状态。`);
    }
    catch (error) {
        if (!reviewRequestIsCurrent(guard))
            return;
        const failure = failureDetails(error, "HUMAN_REVIEW_CLAIM_FAILED");
        if ([
            "HUMAN_REVIEW_CLAIM_REPLAY_STALE",
            "HUMAN_REVIEW_TASK_VERSION_CONFLICT",
            "HUMAN_REVIEW_TASK_ALREADY_CLAIMED",
            "HUMAN_REVIEW_TASK_NOT_CLAIMABLE",
        ].includes(failure.code)) {
            if (discardReviewClaim(task.task_id)) {
                setReviewTasks((current) => current.filter((candidate) => candidate.task_id !== task.task_id));
                setSelectedReviewTaskId("");
                setFeedback(`${failure.code}；本地领取恢复已清除，请刷新队列后重试。`);
            }
            else {
                setFeedback(`${failure.code}；HUMAN_REVIEW_CLAIM_RECOVERY_DISCARD_FAILED`);
            }
        }
        else {
            setFeedback(failure.code);
        }
    }
    finally {
        finishReviewRequest(guard);
    }
      } catch (err) {
        console.warn("claimReviewTask execution warning:", err);
      }
    },
    correctionValue() {
      const fileInput = this.data.fileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = this.data.folderInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = this.data.fileAdditionLock || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = this.data.fileAdditionOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = this.data.selectionCapacity || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = this.data.recoveryByScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = this.data.recoveryLoad || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = this.data.reviewScopeGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = this.data.reviewRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = this.data.reviewEngineScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = this.data.recoveryIdentityGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = this.data.activeIdentityScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = this.data.intakeBusyOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = this.data.estimateRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = this.data.intakeProjectGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = this.data.activeProjectId || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        if (!correctionTouched)
        throw new Error("HUMAN_REVIEW_CORRECTION_REQUIRED");
    if (selectedReviewTask()?.target_kind === "TEXT")
        return correction;
    try {
        return parseStrictJson(correction);
    }
    catch (error) {
        if (error instanceof StrictJsonError) {
            throw new Error(`HUMAN_REVIEW_CORRECTION_${error.code}`);
        }
        throw error;
    }
      } catch (err) {
        console.warn("correctionValue execution warning:", err);
      }
    },
    async editReviewTask() {
      const fileInput = this.data.fileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = this.data.folderInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = this.data.fileAdditionLock || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = this.data.fileAdditionOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = this.data.selectionCapacity || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = this.data.recoveryByScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = this.data.recoveryLoad || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = this.data.reviewScopeGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = this.data.reviewRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = this.data.reviewEngineScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = this.data.recoveryIdentityGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = this.data.activeIdentityScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = this.data.intakeBusyOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = this.data.estimateRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = this.data.intakeProjectGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = this.data.activeProjectId || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        const task = selectedReviewTask();
    const claim = task ? reviewClaims[task.task_id] : undefined;
    if (!task || !claim || claim.fence === undefined
        || !validReviewClaim(claim, reviewIdentityScope)
        || !exactRequiredText(reviewReason.trim(), 2_000)) {
        setFeedback("HUMAN_REVIEW_TASK_CLAIM_REQUIRED");
        return;
    }
    const guard = beginReviewRequest();
    setFeedback("");
    try {
        const correctedValue = correctionValue();
        const correctionReason = reviewReason.trim();
        const editInput = {
            task_id: task.task_id,
            expected_version: task.version,
            expected_correction_version: task.current_correction_version,
            claim_token: claim.token,
            claim_fence: claim.fence,
            correction: { value: correctedValue, reason: correctionReason },
        };
        const editDigest = await sha256(new TextEncoder().encode(canonicalStrictJson(editInput)).buffer);
        assertReviewRequestCurrent(guard);
        const response = await executeGuardedReviewSkill(guard, "elmos-human-review-and-correction", "edit", editInput, `mmi-review-edit-${editDigest}`);
        const editOutput = exactReviewOutput(response, ["correction", "task"]);
        const edited = await validatedReviewTask(response, guard, {
            priorTask: task,
            taskId: task.task_id,
            assetId: task.asset_id,
            state: "EDITED",
            version: task.version + 1,
            correctionVersion: task.current_correction_version + 1,
            claimFence: claim.fence,
        });
        assertReviewRequestCurrent(guard);
        if (edited.claim_actor_id !== task.claim_actor_id
            || edited.claim_expires_at !== task.claim_expires_at
            || edited.effective_version !== task.effective_version
            || edited.effective_digest !== task.effective_digest
            || !exactReviewCorrection(editOutput.correction, task, edited, correctedValue, correctionReason))
            throw new Error("HUMAN_REVIEW_CORRECTION_RESPONSE_BINDING_INVALID");
        commitReviewTask(edited);
        setReviewCurrentCorrection(editOutput.correction);
        setCorrection("");
        setCorrectionTouched(false);
        setFeedback(`审阅任务 ${edited.task_id} 已创建不可变纠正版本，等待批准或拒绝。`);
    }
    catch (error) {
        if (!reviewRequestIsCurrent(guard))
            return;
        const failure = failureDetails(error, "HUMAN_REVIEW_EDIT_FAILED");
        if ([
            "HUMAN_REVIEW_CLAIM_NOT_OWNED",
            "HUMAN_REVIEW_TASK_VERSION_CONFLICT",
        ].includes(failure.code) && discardReviewClaim(task.task_id)) {
            setReviewTasks((current) => current.filter((candidate) => candidate.task_id !== task.task_id));
            setSelectedReviewTaskId("");
            setFeedback(`${failure.code}；旧身份或任务版本的领取凭证已清除，请刷新队列。`);
        }
        else {
            setFeedback(failure.code);
        }
    }
    finally {
        finishReviewRequest(guard);
    }
      } catch (err) {
        console.warn("editReviewTask execution warning:", err);
      }
    },
    async decideReviewTask(operation) {
      const fileInput = this.data.fileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = this.data.folderInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = this.data.fileAdditionLock || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = this.data.fileAdditionOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = this.data.selectionCapacity || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = this.data.recoveryByScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = this.data.recoveryLoad || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = this.data.reviewScopeGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = this.data.reviewRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = this.data.reviewEngineScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = this.data.recoveryIdentityGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = this.data.activeIdentityScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = this.data.intakeBusyOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = this.data.estimateRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = this.data.intakeProjectGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = this.data.activeProjectId || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        const task = selectedReviewTask();
    const claim = task ? reviewClaims[task.task_id] : undefined;
    const visibleCorrection = task && reviewCurrentCorrection
        && exactCurrentReviewCorrection(reviewCurrentCorrection, task)
        ? reviewCurrentCorrection
        : undefined;
    if (!task
        || !claim
        || claim.fence === undefined
        || !validReviewClaim(claim, reviewIdentityScope)
        || !exactRequiredText(reviewReason.trim(), 2_000)
        || operation === "approve" && task.state !== "EDITED"
        || task.current_correction_version > 0 && visibleCorrection === undefined) {
        setFeedback("HUMAN_REVIEW_TASK_CLAIM_REQUIRED");
        return;
    }
    const guard = beginReviewRequest();
    setFeedback("");
    try {
        const authoritativeCorrection = await fetchCurrentReviewCorrection(guard, task);
        assertReviewRequestCurrent(guard);
        if (canonicalStrictJson(authoritativeCorrection ?? null)
            !== canonicalStrictJson(visibleCorrection ?? null)) {
            setReviewCurrentCorrection(authoritativeCorrection ?? null);
            throw new Error("HUMAN_REVIEW_CURRENT_CORRECTION_CHANGED_REVIEW_REQUIRED");
        }
        const decisionReason = reviewReason.trim();
        const decisionInput = {
            task_id: task.task_id,
            expected_version: task.version,
            claim_token: claim.token,
            claim_fence: claim.fence,
            reason: decisionReason,
        };
        const decisionDigest = await sha256(new TextEncoder().encode(canonicalStrictJson(decisionInput)).buffer);
        assertReviewRequestCurrent(guard);
        const response = await executeGuardedReviewSkill(guard, "elmos-human-review-and-correction", operation, decisionInput, `mmi-review-${operation}-${decisionDigest}`);
        const decisionOutput = exactReviewOutput(response, ["decision", "propagations", "task"]);
        const decisionDocument = decisionOutput.decision;
        const propagations = decisionOutput.propagations;
        const decided = await validatedReviewTask(response, guard, {
            priorTask: task,
            taskId: task.task_id,
            assetId: task.asset_id,
            state: operation === "approve" ? "APPROVED" : "REJECTED",
            version: task.version + 1,
            correctionVersion: task.current_correction_version,
            claimFence: claim.fence,
        });
        assertReviewRequestCurrent(guard);
        const trustedActorId = account.status === "authenticated"
            ? account.principal?.actorId
            : undefined;
        if (!exactReviewDecision(decisionDocument, task, decided, operation, decisionReason, authoritativeCorrection, trustedActorId)
            || decided.current_correction_digest !== task.current_correction_digest
            || decided.effective_version !== task.effective_version
            || decided.effective_digest !== task.effective_digest
            || operation === "approve" && !validReviewPropagations(propagations, task.task_id, {
                exactBatch: true,
                direction: "APPLY",
                decisionId: decisionDocument.decision_id,
                correctionVersion: task.current_correction_version,
                initial: true,
            })
            || operation === "reject" && (!Array.isArray(propagations) || propagations.length !== 0))
            throw new Error("HUMAN_REVIEW_DECISION_RESPONSE_BINDING_INVALID");
        commitReviewTask(decided);
        const discarded = discardReviewClaim(task.task_id);
        setReviewPropagation(operation === "approve" ? response : null);
        const message = operation === "approve"
            ? `审阅任务 ${decided.task_id} 已批准；四个派生传播任务已持久排队。`
            : `审阅任务 ${decided.task_id} 已拒绝；纠正历史仍保留。`;
        setFeedback(discarded ? message : `${message} HUMAN_REVIEW_CLAIM_RECOVERY_DISCARD_FAILED`);
    }
    catch (error) {
        if (!reviewRequestIsCurrent(guard))
            return;
        const failure = failureDetails(error, `HUMAN_REVIEW_${operation.toUpperCase()}_FAILED`);
        if ([
            "HUMAN_REVIEW_CLAIM_NOT_OWNED",
            "HUMAN_REVIEW_TASK_VERSION_CONFLICT",
        ].includes(failure.code) && discardReviewClaim(task.task_id)) {
            setReviewTasks((current) => current.filter((candidate) => candidate.task_id !== task.task_id));
            setSelectedReviewTaskId("");
            setFeedback(`${failure.code}；旧身份或任务版本的领取凭证已清除，请刷新队列。`);
        }
        else {
            setFeedback(failure.code);
        }
    }
    finally {
        finishReviewRequest(guard);
    }
      } catch (err) {
        console.warn("decideReviewTask execution warning:", err);
      }
    },
    async transitionClosedReviewTask(operation) {
      const fileInput = this.data.fileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = this.data.folderInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = this.data.fileAdditionLock || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = this.data.fileAdditionOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = this.data.selectionCapacity || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = this.data.recoveryByScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = this.data.recoveryLoad || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = this.data.reviewScopeGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = this.data.reviewRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = this.data.reviewEngineScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = this.data.recoveryIdentityGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = this.data.activeIdentityScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = this.data.intakeBusyOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = this.data.estimateRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = this.data.intakeProjectGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = this.data.activeProjectId || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        const task = selectedReviewTask();
    const visibleCorrection = task && reviewCurrentCorrection
        && exactCurrentReviewCorrection(reviewCurrentCorrection, task)
        ? reviewCurrentCorrection
        : undefined;
    if (!task
        || !exactRequiredText(reviewReason.trim(), 2_000)
        || task.current_correction_version > 0 && visibleCorrection === undefined)
        return;
    const guard = beginReviewRequest();
    setFeedback("");
    try {
        const authoritativeCorrection = await fetchCurrentReviewCorrection(guard, task);
        assertReviewRequestCurrent(guard);
        if (canonicalStrictJson(authoritativeCorrection ?? null)
            !== canonicalStrictJson(visibleCorrection ?? null)) {
            setReviewCurrentCorrection(authoritativeCorrection ?? null);
            throw new Error("HUMAN_REVIEW_CURRENT_CORRECTION_CHANGED_REVIEW_REQUIRED");
        }
        const transitionReason = reviewReason.trim();
        const transitionInput = {
            task_id: task.task_id,
            expected_version: task.version,
            reason: transitionReason,
        };
        const transitionDigest = await sha256(new TextEncoder().encode(canonicalStrictJson(transitionInput)).buffer);
        assertReviewRequestCurrent(guard);
        const response = await executeGuardedReviewSkill(guard, "elmos-human-review-and-correction", operation, transitionInput, `mmi-review-${operation}-${transitionDigest}`);
        const transitionOutput = exactReviewOutput(response, ["decision", "propagations", "task"]);
        const transitionDecision = transitionOutput.decision;
        const transitionPropagations = transitionOutput.propagations;
        const transitioned = await validatedReviewTask(response, guard, {
            priorTask: task,
            taskId: task.task_id,
            assetId: task.asset_id,
            state: operation === "revert" ? "REVERTING" : "REOPENED",
            version: task.version + 1,
            correctionVersion: task.current_correction_version,
            claimFence: task.claim_fence,
        });
        assertReviewRequestCurrent(guard);
        const trustedActorId = account.status === "authenticated"
            ? account.principal?.actorId
            : undefined;
        if (!exactReviewDecision(transitionDecision, task, transitioned, operation, transitionReason, authoritativeCorrection, trustedActorId)
            || transitioned.current_correction_digest !== task.current_correction_digest
            || transitioned.effective_version !== task.effective_version
            || transitioned.effective_digest !== task.effective_digest
            || operation === "revert" && !validReviewPropagations(transitionPropagations, task.task_id, {
                exactBatch: true,
                direction: "REVERT",
                decisionId: transitionDecision.decision_id,
                correctionVersion: task.current_correction_version,
                initial: true,
            })
            || operation === "reopen" && (!Array.isArray(transitionPropagations) || transitionPropagations.length !== 0))
            throw new Error("HUMAN_REVIEW_DECISION_RESPONSE_BINDING_INVALID");
        commitReviewTask(transitioned);
        const discarded = discardReviewClaim(task.task_id);
        setReviewPropagation(operation === "revert" ? response : null);
        const message = operation === "revert"
            ? `审阅任务 ${transitioned.task_id} 已进入可审计回退传播。`
            : `审阅任务 ${transitioned.task_id} 已重新打开。`;
        setFeedback(discarded ? message : `${message} HUMAN_REVIEW_CLAIM_RECOVERY_DISCARD_FAILED`);
    }
    catch (error) {
        if (reviewRequestIsCurrent(guard)) {
            setFeedback(error instanceof Error ? error.message : `HUMAN_REVIEW_${operation.toUpperCase()}_FAILED`);
        }
    }
    finally {
        finishReviewRequest(guard);
    }
      } catch (err) {
        console.warn("transitionClosedReviewTask execution warning:", err);
      }
    },
    async refreshReviewPropagation() {
      const fileInput = this.data.fileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = this.data.folderInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = this.data.fileAdditionLock || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = this.data.fileAdditionOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = this.data.selectionCapacity || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = this.data.recoveryByScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = this.data.recoveryLoad || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = this.data.reviewScopeGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = this.data.reviewRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = this.data.reviewEngineScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = this.data.recoveryIdentityGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = this.data.activeIdentityScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = this.data.intakeBusyOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = this.data.estimateRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = this.data.intakeProjectGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = this.data.activeProjectId || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        const task = selectedReviewTask();
    if (!task)
        return;
    const guard = beginReviewRequest();
    setFeedback("");
    try {
        const response = await executeGuardedReviewSkill(guard, "elmos-human-review-and-correction", "propagation_status", { task_id: task.task_id }, `mmi-review-propagation-${task.task_id}-${crypto.randomUUID()}`);
        const statusOutput = exactReviewOutput(response, ["effective", "propagations", "task"]);
        const statusTask = await validatedReviewTask(response, guard, {
            priorTask: task,
            taskId: task.task_id,
            assetId: task.asset_id,
            minimumVersion: task.version,
        });
        assertReviewRequestCurrent(guard);
        if (!validHistoricalPropagationBatches(statusOutput.propagations, task.task_id)) {
            throw new Error("HUMAN_REVIEW_PROPAGATION_RESPONSE_BINDING_INVALID");
        }
        if (!exactReviewEffective(statusOutput.effective, statusTask, statusOutput.propagations)) {
            throw new Error("HUMAN_REVIEW_EFFECTIVE_RESPONSE_INVALID");
        }
        commitReviewTask(statusTask);
        setReviewPropagation(response);
        setFeedback(`审阅任务 ${task.task_id} 的传播状态已刷新。`);
    }
    catch (error) {
        if (reviewRequestIsCurrent(guard)) {
            setFeedback(error instanceof Error ? error.message : "HUMAN_REVIEW_PROPAGATION_STATUS_FAILED");
        }
    }
    finally {
        finishReviewRequest(guard);
    }
      } catch (err) {
        console.warn("refreshReviewPropagation execution warning:", err);
      }
    },
    async submitCorrection() {
      const fileInput = this.data.fileInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const folderInput = this.data.folderInput || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionLock = this.data.fileAdditionLock || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const fileAdditionOwner = this.data.fileAdditionOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const selectionCapacity = this.data.selectionCapacity || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryByScope = this.data.recoveryByScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryLoad = this.data.recoveryLoad || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewScopeGeneration = this.data.reviewScopeGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewRequestOwner = this.data.reviewRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const reviewEngineScope = this.data.reviewEngineScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const recoveryIdentityGeneration = this.data.recoveryIdentityGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeIdentityScope = this.data.activeIdentityScope || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeBusyOwner = this.data.intakeBusyOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const estimateRequestOwner = this.data.estimateRequestOwner || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const intakeProjectGeneration = this.data.intakeProjectGeneration || { current: { focus: () => {}, scrollIntoView: () => {} } };
      const activeProjectId = this.data.activeProjectId || { current: { focus: () => {}, scrollIntoView: () => {} } };
      try {
        const target = assets.find((asset) => asset.assetId === correctionTarget);
    if (!target || !correctionTouched)
        return;
    const currentVersion = target.assetVersion;
    if (!currentVersion) {
        setFeedback("ASSET_VERSION_REQUIRED_FOR_CORRECTION");
        return;
    }
    let identityGuard;
    try {
        identityGuard = captureIntakeIdentity();
    }
    catch (error) {
        setFeedback(error instanceof Error ? error.message : "MULTIMODAL_IDENTITY_SCOPE_UNAVAILABLE");
        return;
    }
    const guard = beginReviewRequest();
    try {
        const correctionInput = {
            content_id: target.assetId,
            expected_version: currentVersion,
            value: correction,
            reason: "USER_REVIEW",
        };
        const correctionDigest = await sha256(new TextEncoder().encode(canonicalStrictJson(correctionInput)).buffer);
        assertReviewRequestCurrent(guard);
        const response = await executeGuardedReviewSkill(guard, "elmos-human-review-and-correction", "correct", correctionInput, `mmi-correction-${correctionDigest}`);
        const corrected = outputRecord(response, "correction");
        const persistedAssetStatus = responseString(response, "asset_status");
        const correctedPhase = persistedAssetStatus
            ? phaseFrom({ status: persistedAssetStatus })
            : phaseFrom(response);
        update(target.key, {
            phase: correctedPhase,
            response,
            code: undefined,
            recoveryAttached: !["READY", "QUARANTINED"].includes(correctedPhase),
            assetVersion: positiveInteger(corrected?.version) ?? currentVersion,
        });
        setCorrection("");
        setCorrectionTouched(false);
        if (["READY", "QUARANTINED"].includes(correctedPhase) && target.projectId && target.engineProjectId) {
            try {
                await clearRecovery(target, identityGuard);
                assertReviewRequestCurrent(guard);
            }
            catch {
                if (reviewRequestIsCurrent(guard)) {
                    setFeedback("CORRECTION_APPLIED_RECOVERY_CLEANUP_FAILED");
                }
                return;
            }
        }
        setFeedback("纠错版本已提交；原始资产未被覆盖。");
    }
    catch (error) {
        if (reviewRequestIsCurrent(guard)) {
            setFeedback(error instanceof Error ? error.message : "CORRECTION_FAILED");
        }
    }
    finally {
        finishReviewRequest(guard);
    }
      } catch (err) {
        console.warn("submitCorrection execution warning:", err);
      }
    },
  },
});
