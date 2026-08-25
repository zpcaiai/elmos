package dev.elmos.intake;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.math.BigDecimal;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Duration;
import java.time.OffsetDateTime;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.Base64;
import java.util.Collections;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.Flow;
import java.util.regex.Pattern;

/** Bounded HTTP client with fail-closed request and response contract validation. */
public final class MultimodalIntakeClient {
  public static final String CAPABILITIES_PATH = "/api/v1/multimodal-intake/capabilities";
  public static final String EXECUTE_PATH = "/api/v1/multimodal-intake/execute";
  public static final String PROGRESS_TASK_EVENTS_PREFIX = "/api/v1/multimodal-intake/progress/tasks/";
  public static final String PROGRESS_JOB_EVENTS_PREFIX = "/api/v1/multimodal-intake/progress/jobs/";
  public static final String PROGRESS_TASK_WEBSOCKET_PREFIX = "/api/v1/multimodal-intake/progress/ws/tasks/";
  public static final String PROGRESS_JOB_WEBSOCKET_PREFIX = "/api/v1/multimodal-intake/progress/ws/jobs/";
  public static final Set<String> SUPPORTED_PROGRESS_TRANSPORTS = Set.of("sse");
  public static final boolean WEBSOCKET_PROGRESS_SUPPORTED = false;
  public static final Map<String, Set<String>> OPERATION_REGISTRY = Map.ofEntries(
      Map.entry("elmos-multimodal-input-orchestrator", Set.of("bootstrap_project", "cancel_job", "create_session", "get_session", "process_session", "resume_job")),
      Map.entry("elmos-secure-resumable-upload", Set.of("abort", "commit", "start", "status", "upload_part")),
      Map.entry("elmos-file-type-detection-and-validation", Set.of("inspect", "process_asset")),
      Map.entry("elmos-malware-quarantine-and-sandbox", Set.of("inspect", "process_asset")),
      Map.entry("elmos-audio-asr-and-diarization", Set.of("parse", "process_asset")),
      Map.entry("elmos-image-ocr-and-preprocessing", Set.of("parse", "process_asset")),
      Map.entry("elmos-visual-ui-understanding", Set.of("parse", "process_asset", "understand")),
      Map.entry("elmos-diagram-and-architecture-understanding", Set.of("parse", "process_asset", "understand")),
      Map.entry("elmos-pdf-layout-table-parser", Set.of("parse", "process_asset")),
      Map.entry("elmos-word-document-parser", Set.of("parse", "process_asset")),
      Map.entry("elmos-markdown-text-log-parser", Set.of("parse", "process_asset")),
      Map.entry("elmos-unified-multimodal-content-ir", Set.of("normalize")),
      Map.entry("elmos-source-anchor-and-provenance", Set.of("anchor")),
      Map.entry("elmos-multimodal-requirement-extraction", Set.of("extract")),
      Map.entry("elmos-multi-asset-content-fusion", Set.of("fuse")),
      Map.entry("elmos-document-version-and-conflict-detection", Set.of("detect_conflicts")),
      Map.entry("elmos-human-review-and-correction", Set.of("approve", "claim", "correct", "current_correction", "edit", "enqueue", "enqueue_execute", "enqueue_prepare", "get", "list", "propagation_claim", "propagation_complete", "propagation_dispatch", "propagation_reconcile", "propagation_status", "reject", "reopen", "reservation_status", "revert", "source_get", "source_list", "source_register")),
      Map.entry("elmos-prompt-injection-defense", Set.of("evaluate")),
      Map.entry("elmos-provider-routing-and-fallback", Set.of("route")),
      Map.entry("elmos-storage-index-and-retrieval", Set.of("delete", "query", "rebuild_status", "repair", "upsert")),
      Map.entry("elmos-durable-processing-and-recovery", Set.of("get_task_state", "list_outbox", "mark_outbox_published", "process_durable_transition", "transition")),
      Map.entry("elmos-processing-cost-and-eta-estimation", Set.of("estimate")),
      Map.entry("elmos-multimodal-observability", Set.of("observe")),
      Map.entry("elmos-multimodal-evaluation-framework", Set.of("catalog", "evaluate", "get_run", "verify")),
      Map.entry("elmos-multimodal-input-workbench-ui", Set.of("build_preview", "capabilities", "describe", "health")),
      Map.entry("elmos-ingestion-api-and-sdk", Set.of("build_contract", "capabilities", "describe", "health")),
      Map.entry("elmos-data-retention-and-governance", Set.of("delete", "delete_status", "evaluate", "export", "provider_access")),
      Map.entry("elmos-downstream-agent-integration", Set.of("build_context", "get_context", "get_grant", "link_result", "list_result_links", "revoke_grant")),
      Map.entry("elmos-codex-context-capacity-parity", Set.of("check")),
      Map.entry("elmos-context-budget-manager", Set.of("calculate")),
      Map.entry("elmos-multimodal-token-accounting", Set.of("account")),
      Map.entry("elmos-long-context-packing-and-ranking", Set.of("pack")),
      Map.entry("elmos-context-pressure-monitor", Set.of("monitor")),
      Map.entry("elmos-structured-context-compaction", Set.of("compact")),
      Map.entry("elmos-context-checkpoint-and-recovery", Set.of("create", "diff", "list", "restore", "rollback")),
      Map.entry("elmos-context-rehydration", Set.of("rehydrate")),
      Map.entry("elmos-project-memory-and-retrieval", Set.of("delete", "query", "rebuild_status", "repair", "write")),
      Map.entry("elmos-repository-context-map", Set.of("rebuild", "rollback", "status")),
      Map.entry("elmos-model-capability-discovery", Set.of("discover", "history", "rollback")),
      Map.entry("elmos-context-integrity-and-loss-detection", Set.of("verify")),
      Map.entry("elmos-folder-tree-input", Set.of("append", "begin", "finalize", "page", "status")),
      Map.entry("elmos-resumable-multi-file-folder-upload", Set.of("confirm_part", "negotiate", "status")),
      Map.entry("elmos-project-package-manifest", Set.of("diff", "finalize", "page")),
      Map.entry("elmos-secure-zip-tar-extraction", Set.of("expand_nested", "extract", "publish")),
      Map.entry("elmos-archive-bomb-and-path-traversal-defense", Set.of("inspect")),
      Map.entry("elmos-project-root-language-framework-detection", Set.of("rebuild", "rollback", "status")),
      Map.entry("elmos-ignore-generated-vendored-file-classification", Set.of("rebuild", "rollback", "status")),
      Map.entry("elmos-repository-map-and-symbol-indexing", Set.of("rebuild", "rollback", "status")),
      Map.entry("elmos-project-package-version-and-incremental-update", Set.of("diff")),
      Map.entry("elmos-project-package-preview-and-review-ui", Set.of("override", "page", "undo"))
  );

  public record InputFieldContract(Set<String> allowed, Set<String> required) {}

  /** Exact request fields for the typed lifecycle and evaluation surfaces. */
  public static final Map<String, InputFieldContract> INPUT_FIELD_CONTRACTS = Map.ofEntries(
      Map.entry("elmos-multimodal-evaluation-framework/evaluate", inputContract("subject evidence", "subject evidence")),
      Map.entry("elmos-multimodal-evaluation-framework/verify", inputContract("run_id", "run_id")),
      Map.entry("elmos-multimodal-evaluation-framework/get_run", inputContract("run_id", "run_id")),
      Map.entry("elmos-multimodal-evaluation-framework/catalog", inputContract("", "")),
      Map.entry("elmos-multimodal-requirement-extraction/extract", inputContract("sources package_version projection_key task_id", "package_version")),
      Map.entry("elmos-multi-asset-content-fusion/fuse", inputContract("assets package_version projection_key task_id", "package_version")),
      Map.entry("elmos-document-version-and-conflict-detection/detect_conflicts", inputContract("claims package_version projection_key task_id", "package_version")),
      Map.entry("elmos-downstream-agent-integration/build_context", inputContract("task_id subject_id package_version source_receipt_ids tool_receipt_ids", "task_id subject_id package_version source_receipt_ids")),
      Map.entry("elmos-downstream-agent-integration/get_context", inputContract("context_id", "context_id")),
      Map.entry("elmos-downstream-agent-integration/get_grant", inputContract("context_id grant_id", "context_id grant_id")),
      Map.entry("elmos-downstream-agent-integration/revoke_grant", inputContract("context_id grant_id reason", "context_id grant_id reason")),
      Map.entry("elmos-downstream-agent-integration/link_result", inputContract("context_id grant_id result_receipt_id", "context_id grant_id result_receipt_id")),
      Map.entry("elmos-downstream-agent-integration/list_result_links", inputContract("context_id", "context_id")),
      Map.entry("elmos-codex-context-capacity-parity/check", inputContract("capability_snapshot task_id", "")),
      Map.entry("elmos-context-budget-manager/calculate", inputContract("capability_snapshot reserved_output_tokens safety_headroom_tokens usage task_id", "")),
      Map.entry("elmos-multimodal-token-accounting/account", inputContract("estimator_version items model_id model_version tokenizer_id tokenizer_version task_id current_window_output_reserved_tokens model_snapshot_id", "")),
      Map.entry("elmos-long-context-packing-and-ranking/pack", inputContract("candidates effective_input_budget task_id", "")),
      Map.entry("elmos-context-pressure-monitor/monitor", inputContract("effective_input_budget previous_state used_tokens task_id forecast_horizon next_turn_tokens pending_tool_tokens pending_test_log_tokens", "")),
      Map.entry("elmos-structured-context-compaction/compact", inputContract("source_history_digest state task_id raw_history package_version model_snapshot_id rollback_checkpoint_id side_effect_cursor cost_cursor input_tokens output_tokens", "")),
      Map.entry("elmos-context-checkpoint-and-recovery/create", inputContract("state payload task_id raw_history package_version model_snapshot_id rollback_checkpoint_id side_effect_cursor cost_cursor input_tokens output_tokens", "")),
      Map.entry("elmos-context-checkpoint-and-recovery/list", inputContract("task_id", "")),
      Map.entry("elmos-context-checkpoint-and-recovery/diff", inputContract("left_checkpoint_id right_checkpoint_id task_id", "left_checkpoint_id right_checkpoint_id")),
      Map.entry("elmos-context-checkpoint-and-recovery/restore", inputContract("checkpoint_id task_id", "checkpoint_id")),
      Map.entry("elmos-context-checkpoint-and-recovery/rollback", inputContract("checkpoint_id task_id", "checkpoint_id")),
      Map.entry("elmos-context-rehydration/rehydrate", inputContract("package_version remaining_budget_tokens source_ids task_id", "")),
      Map.entry("elmos-model-capability-discovery/discover", inputContract("observation previous_snapshot task_id", "")),
      Map.entry("elmos-model-capability-discovery/history", inputContract("provider model_id", "provider model_id")),
      Map.entry("elmos-model-capability-discovery/rollback", inputContract("snapshot_id", "snapshot_id")),
      Map.entry("elmos-context-integrity-and-loss-detection/verify", inputContract("after before task_id checkpoint_id", "")),
      Map.entry("elmos-repository-context-map/rebuild", inputContract("package_version source_input", "package_version source_input")),
      Map.entry("elmos-repository-context-map/status", inputContract("package_version", "package_version")),
      Map.entry("elmos-repository-context-map/rollback", inputContract("package_version artifact_version", "package_version artifact_version")),
      Map.entry("elmos-folder-tree-input/begin", inputContract("session_id expected_entry_count", "expected_entry_count")),
      Map.entry("elmos-folder-tree-input/append", inputContract("session_id chunk_index entries", "session_id chunk_index entries")),
      Map.entry("elmos-folder-tree-input/finalize", inputContract("session_id", "session_id")),
      Map.entry("elmos-folder-tree-input/status", inputContract("session_id", "session_id")),
      Map.entry("elmos-folder-tree-input/page", inputContract("package_version limit cursor", "package_version")),
      Map.entry("elmos-resumable-multi-file-folder-upload/negotiate", inputContract("session_id path byte_count content_digest part_size", "session_id path byte_count content_digest")),
      Map.entry("elmos-resumable-multi-file-folder-upload/confirm_part", inputContract("session_id path part_number byte_count part_digest data_base64", "session_id path part_number byte_count part_digest data_base64")),
      Map.entry("elmos-resumable-multi-file-folder-upload/status", inputContract("session_id path", "session_id")),
      Map.entry("elmos-project-package-manifest/finalize", inputContract("session_id", "session_id")),
      Map.entry("elmos-project-package-manifest/page", inputContract("package_version limit cursor", "package_version")),
      Map.entry("elmos-project-package-manifest/diff", inputContract("old_version new_version", "old_version new_version")),
      Map.entry("elmos-project-package-version-and-incremental-update/diff", inputContract("old_version new_version", "old_version new_version")),
      Map.entry("elmos-project-package-preview-and-review-ui/page", inputContract("package_version limit cursor", "package_version")),
      Map.entry("elmos-project-package-preview-and-review-ui/override", inputContract("package_version path expected_override_version role model_read_allowed reason", "package_version path expected_override_version reason")),
      Map.entry("elmos-project-package-preview-and-review-ui/undo", inputContract("package_version path expected_override_version audit_id reason", "package_version path expected_override_version audit_id reason")),
      Map.entry("elmos-project-root-language-framework-detection/rebuild", inputContract("package_version source_input", "package_version source_input")),
      Map.entry("elmos-project-root-language-framework-detection/status", inputContract("package_version", "package_version")),
      Map.entry("elmos-project-root-language-framework-detection/rollback", inputContract("package_version artifact_version", "package_version artifact_version")),
      Map.entry("elmos-ignore-generated-vendored-file-classification/rebuild", inputContract("package_version source_input", "package_version source_input")),
      Map.entry("elmos-ignore-generated-vendored-file-classification/status", inputContract("package_version", "package_version")),
      Map.entry("elmos-ignore-generated-vendored-file-classification/rollback", inputContract("package_version artifact_version", "package_version artifact_version")),
      Map.entry("elmos-repository-map-and-symbol-indexing/rebuild", inputContract("package_version source_input", "package_version source_input")),
      Map.entry("elmos-repository-map-and-symbol-indexing/status", inputContract("package_version", "package_version")),
      Map.entry("elmos-repository-map-and-symbol-indexing/rollback", inputContract("package_version artifact_version", "package_version artifact_version"))
  );

  private static InputFieldContract inputContract(String allowed, String required) {
    return new InputFieldContract(
        allowed.isEmpty() ? Set.of() : Set.of(allowed.split(" ")),
        required.isEmpty() ? Set.of() : Set.of(required.split(" "))
    );
  }

  public record RegisteredOperation(String skill, String operation) {
    public RegisteredOperation {
      if (!OPERATION_REGISTRY.getOrDefault(skill, Set.of()).contains(operation)) {
        throw new IllegalArgumentException("REQUIRES_ADAPTER");
      }
    }
  }

  public record ExecutionContext(
      String tenantId,
      String projectId,
      String actorId,
      String idempotencyKey,
      String traceId
  ) {}

  public record EvaluationSubject(
      String subjectId,
      String subjectKind,
      String artifactDigest,
      String implementationVersion,
      String configurationDigest
  ) {
    public EvaluationSubject {
      if (!RESOURCE_ID.matcher(Objects.requireNonNull(subjectId, "subjectId")).matches()
          || !Set.of("parser", "provider", "model", "runtime", "configuration").contains(subjectKind)
          || !CONTENT_DIGEST.matcher(Objects.requireNonNull(artifactDigest, "artifactDigest")).matches()
          || !RESOURCE_ID.matcher(Objects.requireNonNull(implementationVersion, "implementationVersion")).matches()
          || !CONTENT_DIGEST.matcher(Objects.requireNonNull(configurationDigest, "configurationDigest")).matches()) {
        throw new IllegalArgumentException("OPERATION_INPUT_SHAPE_INVALID");
      }
    }

    public Map<String, Object> toMap() {
      return Map.of(
          "subject_id", subjectId,
          "subject_kind", subjectKind,
          "artifact_digest", artifactDigest,
          "implementation_version", implementationVersion,
          "configuration_digest", configurationDigest
      );
    }
  }

  public record EvaluationEvidence(String caseId, String mediaType, String contentBase64) {
    public EvaluationEvidence {
      if (!RESOURCE_ID.matcher(Objects.requireNonNull(caseId, "caseId")).matches()
          || !boundedText(mediaType, 256)
          || !boundedText(contentBase64, 16 * 1024 * 1024)) {
        throw new IllegalArgumentException("OPERATION_INPUT_SHAPE_INVALID");
      }
      try {
        Base64.getDecoder().decode(contentBase64);
      } catch (IllegalArgumentException error) {
        throw new IllegalArgumentException("OPERATION_INPUT_SHAPE_INVALID", error);
      }
    }

    public Map<String, Object> toMap() {
      return Map.of("case_id", caseId, "media_type", mediaType, "content_base64", contentBase64);
    }
  }

  public record ProjectPackageEntry(
      String path,
      String kind,
      Long byteCount,
      String contentDigest,
      String role,
      Boolean modelReadAllowed,
      Map<String, Object> metadata
  ) {
    public ProjectPackageEntry {
      if (!boundedText(path, 4096)
          || kind != null && !Set.of("file", "directory", "symlink", "hardlink", "special").contains(kind)
          || byteCount != null && (byteCount < 0 || byteCount > MAX_SAFE_JSON_INTEGER)
          || contentDigest != null && !CONTENT_DIGEST.matcher(contentDigest).matches()
          || role != null && !Set.of("PRIMARY", "REFERENCE", "IGNORE").contains(role)) {
        throw new IllegalArgumentException("OPERATION_INPUT_SHAPE_INVALID");
      }
      metadata = metadata == null ? null : Collections.unmodifiableMap(new LinkedHashMap<>(metadata));
    }

    public Map<String, Object> toMap() {
      var value = new LinkedHashMap<String, Object>();
      value.put("path", path);
      if (kind != null) value.put("kind", kind);
      if (byteCount != null) value.put("byte_count", byteCount);
      if (contentDigest != null) value.put("content_digest", contentDigest);
      if (role != null) value.put("role", role);
      if (modelReadAllowed != null) value.put("model_read_allowed", modelReadAllowed);
      if (metadata != null) value.put("metadata", metadata);
      return value;
    }
  }
  public static final String HUMAN_REVIEW_SKILL = "elmos-human-review-and-correction";
  public static final String HUMAN_REVIEW_SOURCE_LIST_OPERATION = "source_list";
  public static final String HUMAN_REVIEW_SOURCE_GET_OPERATION = "source_get";
  public static final String HUMAN_REVIEW_SOURCE_BOUND_ENQUEUE_OPERATION = "enqueue";
  public static final String HUMAN_REVIEW_ENQUEUE_PREPARE_OPERATION = "enqueue_prepare";
  public static final String HUMAN_REVIEW_ENQUEUE_EXECUTE_OPERATION = "enqueue_execute";
  public static final String HUMAN_REVIEW_ORIGINAL_VALUE_DIGEST_CONTRACT =
      "sha256:rfc8785-ijson-safeint-v1";
  public static final int HUMAN_REVIEW_SOURCE_LIST_MAX_ITEMS = 200;
  public static final int HUMAN_REVIEW_SOURCE_COLLECTION_MAX_ITEMS = 1_000;
  public static final Set<String> HUMAN_REVIEW_SOURCE_REF_V2_FIELDS = Set.of(
      "schema_version", "content_id", "content_version", "content_digest", "asset_sha256",
      "target_kind", "target_digest", "snapshot_id", "snapshot_digest", "head_version",
      "head_value_digest", "source_digest", "provenance_digest",
      "original_value_client_digest", "original_value_digest_contract"
  );
  public static final Set<String> HUMAN_REVIEW_SOURCE_SUMMARY_FIELDS = Set.of(
      "schema_version", "content_id", "content_version", "target_kind", "target",
      "target_digest", "confidence", "head_version", "head_direction",
      "head_correction_version", "original_value_client_digest",
      "original_value_digest_contract", "source_ref"
  );
  public static final Set<String> HUMAN_REVIEW_SOURCE_DETAIL_FIELDS = Set.of(
      "schema_version", "content_id", "content_version", "target_kind", "target",
      "target_digest", "confidence", "head_version", "head_direction",
      "head_correction_version", "original_value_client_digest",
      "original_value_digest_contract", "source_ref", "original_value"
  );
  public static final Set<String> HUMAN_REVIEW_SOURCE_BOUND_ENQUEUE_FIELDS = Set.of(
      "content_id", "expected_asset_version", "target_kind", "target_digest",
      "expected_head_version", "expected_snapshot_id", "expected_snapshot_digest",
      "expected_head_value_digest", "original_value_digest", "reason"
  );
  public static final Set<String> HUMAN_REVIEW_ENQUEUE_PREPARE_FIELDS = Set.of(
      "content_id", "expected_asset_version", "target_kind", "target_digest",
      "expected_head_version", "expected_snapshot_id", "expected_snapshot_digest",
      "expected_head_value_digest", "original_value_digest", "reason",
      "recovery_handle", "execute_idempotency_key"
  );
  public static final Set<String> HUMAN_REVIEW_ENQUEUE_EXECUTE_FIELDS = Set.of(
      "recovery_handle"
  );
  public static final Set<String> HUMAN_REVIEW_ENQUEUE_PREPARATION_FIELDS = Set.of(
      "schema_version", "recovery_handle", "request_digest", "state", "safe_to_clear",
      "expires_at", "prepared_at", "executed_at", "task_id", "enqueue_input"
  );
  public static final Set<String> HUMAN_REVIEW_ENQUEUE_PREPARATION_ABSENCE_FIELDS = Set.of(
      "schema_version", "recovery_handle", "state", "safe_to_clear"
  );
  private static final int MAX_RESPONSE_BYTES = 4 * 1024 * 1024;
  private static final int MAX_REQUEST_BYTES = 2 * 1024 * 1024;
  private static final int MAX_JSON_DEPTH = 32;
  private static final int MAX_JSON_NODES = 200_000;
  private static final int MAX_PROGRESS_DOCUMENTS = 64;
  private static final long MAX_SAFE_JSON_INTEGER = 9_007_199_254_740_991L;
  private static final int MIN_TOKEN_LENGTH = 32;
  private static final int MAX_TOKEN_LENGTH = 4096;
  private static final Duration MIN_TIMEOUT = Duration.ofSeconds(1);
  private static final Duration MAX_TIMEOUT = Duration.ofMinutes(2);
  private static final Pattern JSON_SUFFIX_MEDIA_TYPE = Pattern.compile(
      "application/[a-z0-9!#$%&'*.^_`|~-]+\\+json"
  );
  private static final Pattern RESOURCE_ID = Pattern.compile("[A-Za-z0-9][A-Za-z0-9._:-]{0,127}");
  private static final Pattern PROGRESS_CURSOR = Pattern.compile("p1-([1-9][0-9]{0,15})-([0-9a-f]{64})");
  private static final Pattern CONTENT_DIGEST = Pattern.compile("sha256:([0-9a-f]{64})");
  private static final Pattern PUBLIC_CODE = Pattern.compile("[A-Z][A-Z0-9_:-]{0,127}");
  private static final Pattern SKILL = Pattern.compile("elmos-[a-z0-9]+(?:-[a-z0-9]+)*");
  private static final Pattern OPERATION = Pattern.compile("[a-z][a-z0-9_-]{0,63}");
  private static final Pattern HANDLER = Pattern.compile("execute_[a-z0-9_]+");
  private static final Pattern ACTOR_ID = Pattern.compile("[A-Za-z0-9][A-Za-z0-9._:@/-]{0,199}");
  private static final Pattern DIGEST = Pattern.compile("[0-9a-f]{64}");
  private static final Set<String> EXECUTION_STATES = Set.of(
      "SUCCEEDED", "PARTIAL", "BLOCKED", "FAILED", "NOT_APPLICABLE", "NOT_RUN_EXTERNAL"
  );
  private static final Set<String> CAPABILITY_PHASES = Set.of(
      "secure-intake", "normalization", "content", "project-package", "governance",
      "indexing", "context", "review", "delivery", "evaluation"
  );
  private static final String EXPECTED_CAPABILITY_CATALOG_DIGEST =
      "546ec5aae1d7a031b00abab4cd96b3a5c3968ee5e947f7a6c68aeecbe7599d3a";
  private static final String EXPECTED_CAPABILITY_DOCUMENT_DIGEST =
      "bd72f6fb88eb1daf6da13f9552508cca6c7df3a2fd7318299647450114693a8c";
  private static final Set<String> TASK_STATES = Set.of(
      "PENDING", "RUNNING", "PAUSED", "SUCCEEDED", "FAILED_RETRYABLE", "FAILED_FINAL", "CANCELLED"
  );
  private static final Map<String, Set<String>> TASK_TRANSITIONS = Map.of(
      "PENDING", Set.of("RUNNING", "CANCELLED"),
      "RUNNING", Set.of("PAUSED", "SUCCEEDED", "FAILED_RETRYABLE", "FAILED_FINAL", "CANCELLED"),
      "PAUSED", Set.of("RUNNING", "CANCELLED"),
      "FAILED_RETRYABLE", Set.of("RUNNING", "FAILED_FINAL", "CANCELLED"),
      "SUCCEEDED", Set.of(),
      "FAILED_FINAL", Set.of(),
      "CANCELLED", Set.of()
  );
  private static final Map<String, String> JOB_RESULT_BY_STATE = Map.of(
      "QUEUED", "NOT_RUN",
      "RUNNING", "NOT_RUN",
      "COMPLETED", "PASSED",
      "PARTIAL", "PARTIAL",
      "NEEDS_REVIEW", "NEEDS_REVIEW",
      "BLOCKED", "BLOCKED",
      "FAILED", "FAILED",
      "CANCELLED", "BLOCKED"
  );
  private final URI baseUri;
  private final String bearerToken;
  private final Duration requestTimeout;
  private final HttpClient http;

  /**
   * Consume an HTTP body without an early-return streaming handler. HttpClient
   * therefore keeps the request
   * timeout active until the bounded body subscriber completes, while a
   * hostile peer can never make the SDK buffer more than the public response
   * limit.
   */
  private static final class BoundedBodySubscriber implements HttpResponse.BodySubscriber<byte[]> {
    private final int maximumBytes;
    private final String tooLargeCode;
    private final ByteArrayOutputStream output = new ByteArrayOutputStream();
    private final CompletableFuture<byte[]> body = new CompletableFuture<>();
    private Flow.Subscription subscription;
    private int observed;
    private boolean terminal;

    private BoundedBodySubscriber(int maximumBytes, String tooLargeCode) {
      this.maximumBytes = maximumBytes;
      this.tooLargeCode = tooLargeCode;
    }

    @Override
    public CompletionStage<byte[]> getBody() {
      return body;
    }

    @Override
    public void onSubscribe(Flow.Subscription candidate) {
      Objects.requireNonNull(candidate, "subscription");
      if (subscription != null || terminal) {
        candidate.cancel();
        return;
      }
      subscription = candidate;
      candidate.request(1);
    }

    @Override
    public void onNext(List<ByteBuffer> buffers) {
      if (terminal) return;
      try {
        for (var buffer : buffers) {
          while (buffer.hasRemaining()) {
            var count = Math.min(buffer.remaining(), 64 * 1024);
            if ((long) observed + count > maximumBytes) {
              fail(new IOException(tooLargeCode));
              return;
            }
            var chunk = new byte[count];
            buffer.get(chunk);
            output.write(chunk, 0, count);
            observed += count;
          }
        }
        if (!terminal) subscription.request(1);
      } catch (RuntimeException error) {
        fail(error);
      }
    }

    @Override
    public void onError(Throwable error) {
      if (terminal) return;
      terminal = true;
      body.completeExceptionally(error);
    }

    @Override
    public void onComplete() {
      if (terminal) return;
      terminal = true;
      body.complete(output.toByteArray());
    }

    private void fail(Throwable error) {
      if (terminal) return;
      terminal = true;
      if (subscription != null) subscription.cancel();
      body.completeExceptionally(error);
    }
  }

  private static HttpResponse.BodyHandler<byte[]> boundedBodyHandler(String successTooLargeCode) {
    return responseInfo -> new BoundedBodySubscriber(
        MAX_RESPONSE_BYTES,
        responseInfo.statusCode() >= 400
            ? "SDK_ERROR_RESPONSE_TOO_LARGE"
            : successTooLargeCode
    );
  }

  public record ProgressBatch(
      String resourceKind,
      String resourceId,
      List<Map<String, Object>> documents,
      Map<String, Object> heartbeat,
      String requestedCursor,
      String nextCursor
  ) {
    public ProgressBatch {
      documents = documents.stream().map(MultimodalIntakeClient::immutableMap).toList();
      heartbeat = heartbeat == null ? null : immutableMap(heartbeat);
    }
  }

  public record ProgressContext(String tenantId, String projectId, String actorId) {
    public ProgressContext {
      if (tenantId == null
          || !RESOURCE_ID.matcher(tenantId).matches()
          || projectId == null
          || !RESOURCE_ID.matcher(projectId).matches()
          || actorId == null
          || !ACTOR_ID.matcher(actorId).matches()) {
        throw new IllegalArgumentException("SDK_PROGRESS_BOUND_IDENTITY_INVALID");
      }
    }
  }

  public static final class RemoteError extends IOException {
    private static final long serialVersionUID = 1L;
    private final int statusCode;
    private final String code;
    private final boolean retryable;
    private final String traceId;

    private RemoteError(int statusCode, String code, boolean retryable, String traceId) {
      super(code);
      this.statusCode = statusCode;
      this.code = code;
      this.retryable = retryable;
      this.traceId = traceId;
    }

    public int statusCode() { return statusCode; }
    public String code() { return code; }
    public boolean retryable() { return retryable; }
    public String traceId() { return traceId; }
  }

  private record ParsedCursor(long sequence, String digest) {}

  private record ValidatedPreparation(
      Map<String, Object> preparation,
      Map<String, Object> enqueueInput
  ) {}

  private record ExpectedExecutionRequest(
      String skill,
      String operation,
      String tenantId,
      String projectId,
      String actorId,
      String traceId,
      String requestDigest,
      Map<String, Object> input,
      byte[] canonicalBody
  ) {
    ExpectedExecutionRequest {
      input = immutableMap(input);
      canonicalBody = canonicalBody.clone();
    }

    @Override public byte[] canonicalBody() { return canonicalBody.clone(); }
  }

  private static Map<String, Object> immutableMap(Map<String, Object> value) {
    return Collections.unmodifiableMap(new LinkedHashMap<>(value));
  }

  private static String strictResourceId(String value) {
    if (value == null || !RESOURCE_ID.matcher(value).matches()) {
      throw new IllegalArgumentException("SDK_PROGRESS_RESOURCE_ID_INVALID");
    }
    return value;
  }

  private static ParsedCursor strictCursor(String value) {
    if (value == null) return null;
    var matched = PROGRESS_CURSOR.matcher(value);
    if (!value.equals(value.trim()) || !matched.matches()) {
      throw new IllegalArgumentException("SDK_PROGRESS_CURSOR_INVALID");
    }
    try {
      var sequence = Long.parseLong(matched.group(1));
      if (sequence < 1 || sequence > MAX_SAFE_JSON_INTEGER) {
        throw new IllegalArgumentException("SDK_PROGRESS_CURSOR_INVALID");
      }
      return new ParsedCursor(sequence, matched.group(2));
    } catch (NumberFormatException error) {
      throw new IllegalArgumentException("SDK_PROGRESS_CURSOR_INVALID", error);
    }
  }

  private static String strictUtf8(byte[] bytes, String code) throws IOException {
    try {
      return StandardCharsets.UTF_8.newDecoder()
          .onMalformedInput(CodingErrorAction.REPORT)
          .onUnmappableCharacter(CodingErrorAction.REPORT)
          .decode(ByteBuffer.wrap(bytes))
          .toString();
    } catch (CharacterCodingException error) {
      throw new IOException(code, error);
    }
  }

  private static String sha256(String value) throws IOException {
    try {
      var bytes = MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8));
      var result = new StringBuilder(64);
      for (var item : bytes) result.append(String.format(Locale.ROOT, "%02x", item & 0xff));
      return result.toString();
    } catch (NoSuchAlgorithmException error) {
      throw new IOException("SDK_SHA256_UNAVAILABLE", error);
    }
  }

  private static void appendJsonString(StringBuilder target, String value) throws IOException {
    target.append('"');
    for (var index = 0; index < value.length(); index += 1) {
      var character = value.charAt(index);
      if (Character.isHighSurrogate(character)) {
        if (index + 1 >= value.length() || !Character.isLowSurrogate(value.charAt(index + 1))) {
          throw new IOException("SDK_JSON_UNICODE_INVALID");
        }
        target.append(character).append(value.charAt(++index));
      } else if (Character.isLowSurrogate(character)) {
        throw new IOException("SDK_JSON_UNICODE_INVALID");
      } else {
        switch (character) {
          case '"' -> target.append("\\\"");
          case '\\' -> target.append("\\\\");
          case '\b' -> target.append("\\b");
          case '\f' -> target.append("\\f");
          case '\n' -> target.append("\\n");
          case '\r' -> target.append("\\r");
          case '\t' -> target.append("\\t");
          default -> {
            if (character < 0x20) target.append(String.format(Locale.ROOT, "\\u%04x", (int) character));
            else target.append(character);
          }
        }
      }
    }
    target.append('"');
  }

  private static String canonicalDouble(double value) throws IOException {
    if (!Double.isFinite(value)
        || Math.rint(value) == value && Math.abs(value) > MAX_SAFE_JSON_INTEGER) {
      throw new IOException("SDK_JSON_NUMBER_INVALID");
    }
    if (value == 0.0d) return "0";
    var decimal = BigDecimal.valueOf(value).stripTrailingZeros();
    var exponent = decimal.precision() - decimal.scale() - 1;
    if (exponent >= -6 && exponent < 21) return decimal.toPlainString();
    var negative = decimal.signum() < 0;
    var digits = decimal.unscaledValue().abs().toString();
    var coefficient = digits.length() == 1
        ? digits
        : digits.charAt(0) + "." + digits.substring(1);
    return (negative ? "-" : "") + coefficient + "e" + (exponent >= 0 ? "+" : "") + exponent;
  }

  @SuppressWarnings("unchecked")
  private static void appendCanonicalJson(StringBuilder target, Object value) throws IOException {
    if (value == null) target.append("null");
    else if (value instanceof Boolean item) target.append(item ? "true" : "false");
    else if (value instanceof Long item) target.append(item);
    else if (value instanceof Double item) target.append(canonicalDouble(item));
    else if (value instanceof String item) appendJsonString(target, item);
    else if (value instanceof List<?> items) {
      target.append('[');
      for (var index = 0; index < items.size(); index += 1) {
        if (index > 0) target.append(',');
        appendCanonicalJson(target, items.get(index));
      }
      target.append(']');
    } else if (value instanceof Map<?, ?> raw) {
      var object = (Map<String, Object>) raw;
      var keys = new ArrayList<>(object.keySet());
      Collections.sort(keys);
      target.append('{');
      for (var index = 0; index < keys.size(); index += 1) {
        if (index > 0) target.append(',');
        var key = keys.get(index);
        appendJsonString(target, key);
        target.append(':');
        appendCanonicalJson(target, object.get(key));
      }
      target.append('}');
    } else throw new IOException("SDK_JSON_VALUE_INVALID");
  }

  private static String canonicalJson(Object value) throws IOException {
    var result = new StringBuilder();
    appendCanonicalJson(result, value);
    return result.toString();
  }

  private static final class StrictJsonParser {
    private final String source;
    private int offset;
    private int nodes;

    StrictJsonParser(String source) { this.source = source; }

    Object parse() throws IOException {
      var result = value(0);
      whitespace();
      if (offset != source.length()) throw invalid();
      return result;
    }

    private Object value(int depth) throws IOException {
      nodes += 1;
      if (depth > MAX_JSON_DEPTH || nodes > MAX_JSON_NODES) throw new IOException("SDK_JSON_LIMIT_EXCEEDED");
      whitespace();
      if (offset >= source.length()) throw invalid();
      return switch (source.charAt(offset)) {
        case '{' -> object(depth + 1);
        case '[' -> array(depth + 1);
        case '"' -> string();
        case 't' -> literal("true", Boolean.TRUE);
        case 'f' -> literal("false", Boolean.FALSE);
        case 'n' -> literal("null", null);
        default -> number();
      };
    }

    private Map<String, Object> object(int depth) throws IOException {
      offset += 1;
      var result = new LinkedHashMap<String, Object>();
      whitespace();
      if (take('}')) return result;
      while (true) {
        whitespace();
        if (offset >= source.length() || source.charAt(offset) != '"') throw invalid();
        var key = string();
        if (key.isEmpty() || key.getBytes(StandardCharsets.UTF_8).length > 256 || result.containsKey(key)) {
          throw new IOException("SDK_JSON_OBJECT_KEY_INVALID");
        }
        whitespace();
        if (!take(':')) throw invalid();
        result.put(key, value(depth));
        whitespace();
        if (take('}')) return result;
        if (!take(',')) throw invalid();
      }
    }

    private List<Object> array(int depth) throws IOException {
      offset += 1;
      var result = new ArrayList<>();
      whitespace();
      if (take(']')) return result;
      while (true) {
        result.add(value(depth));
        whitespace();
        if (take(']')) return result;
        if (!take(',')) throw invalid();
      }
    }

    private String string() throws IOException {
      if (!take('"')) throw invalid();
      var result = new StringBuilder();
      while (offset < source.length()) {
        var character = source.charAt(offset++);
        if (character == '"') {
          var value = result.toString();
          for (var index = 0; index < value.length(); index += 1) {
            var unit = value.charAt(index);
            if (Character.isHighSurrogate(unit)) {
              if (index + 1 >= value.length() || !Character.isLowSurrogate(value.charAt(++index))) throw invalid();
            } else if (Character.isLowSurrogate(unit)) throw invalid();
          }
          return value;
        }
        if (character < 0x20) throw invalid();
        if (character != '\\') {
          result.append(character);
          continue;
        }
        if (offset >= source.length()) throw invalid();
        var escaped = source.charAt(offset++);
        switch (escaped) {
          case '"', '\\', '/' -> result.append(escaped);
          case 'b' -> result.append('\b');
          case 'f' -> result.append('\f');
          case 'n' -> result.append('\n');
          case 'r' -> result.append('\r');
          case 't' -> result.append('\t');
          case 'u' -> {
            if (offset + 4 > source.length()) throw invalid();
            try { result.append((char) Integer.parseInt(source.substring(offset, offset + 4), 16)); }
            catch (NumberFormatException error) { throw invalid(); }
            offset += 4;
          }
          default -> throw invalid();
        }
      }
      throw invalid();
    }

    private Object number() throws IOException {
      var start = offset;
      if (take('-') && offset >= source.length()) throw invalid();
      if (take('0')) {
        if (offset < source.length() && Character.isDigit(source.charAt(offset))) throw invalid();
      } else {
        if (offset >= source.length() || source.charAt(offset) < '1' || source.charAt(offset) > '9') throw invalid();
        while (offset < source.length() && Character.isDigit(source.charAt(offset))) offset += 1;
      }
      var fractional = false;
      if (take('.')) {
        fractional = true;
        if (offset >= source.length() || !Character.isDigit(source.charAt(offset))) throw invalid();
        while (offset < source.length() && Character.isDigit(source.charAt(offset))) offset += 1;
      }
      if (take('e') || take('E')) {
        fractional = true;
        if (!take('+')) take('-');
        if (offset >= source.length() || !Character.isDigit(source.charAt(offset))) throw invalid();
        while (offset < source.length() && Character.isDigit(source.charAt(offset))) offset += 1;
      }
      try {
        var token = source.substring(start, offset);
        if (!fractional) {
          var integer = Long.parseLong(token);
          if (integer < -MAX_SAFE_JSON_INTEGER || integer > MAX_SAFE_JSON_INTEGER) throw invalid();
          return integer;
        }
        var decimal = Double.parseDouble(token);
        if (!Double.isFinite(decimal)
            || decimal == 0.0d && new BigDecimal(token).compareTo(BigDecimal.ZERO) != 0
            || Math.rint(decimal) == decimal && Math.abs(decimal) > MAX_SAFE_JSON_INTEGER) throw invalid();
        return decimal;
      } catch (NumberFormatException error) {
        throw invalid();
      }
    }

    private Object literal(String text, Object value) throws IOException {
      if (!source.startsWith(text, offset)) throw invalid();
      offset += text.length();
      return value;
    }

    private void whitespace() {
      while (offset < source.length() && " \t\r\n".indexOf(source.charAt(offset)) >= 0) offset += 1;
    }

    private boolean take(char expected) {
      if (offset < source.length() && source.charAt(offset) == expected) {
        offset += 1;
        return true;
      }
      return false;
    }

    private IOException invalid() { return new IOException("SDK_JSON_INVALID"); }
  }

  private static boolean boundedTraceId(Object value) {
    return boundedText(value, 128);
  }

  private static boolean boundedText(Object value, int maximumBytes) {
    if (!(value instanceof String item) || item.isEmpty()
        || item.getBytes(StandardCharsets.UTF_8).length > maximumBytes) return false;
    for (var index = 0; index < item.length(); index += 1) {
      var character = item.charAt(index);
      if (character < 0x20 || character == 0x7f
          || Character.isHighSurrogate(character)
          && (index + 1 >= item.length() || !Character.isLowSurrogate(item.charAt(++index)))
          || Character.isLowSurrogate(character)) return false;
    }
    return true;
  }

  private static boolean hasOuterWhitespace(String value) {
    if (value.isEmpty()) return false;
    var first = value.codePointAt(0);
    var last = value.codePointBefore(value.length());
    return Character.isWhitespace(first) || Character.isSpaceChar(first)
        || Character.isWhitespace(last) || Character.isSpaceChar(last);
  }

  @SuppressWarnings("unchecked")
  private static Map<String, Object> parseStrictObject(byte[] bytes, String invalidCode) throws IOException {
    if (bytes == null || bytes.length == 0 || bytes.length > MAX_RESPONSE_BYTES) {
      throw new IOException(invalidCode);
    }
    var rawJson = strictUtf8(bytes, invalidCode);
    Object parsed;
    try {
      parsed = new StrictJsonParser(rawJson).parse();
    } catch (IOException error) {
      throw new IOException(invalidCode, error);
    }
    if (!(parsed instanceof Map<?, ?> rawMap)) throw new IOException(invalidCode);
    return (Map<String, Object>) rawMap;
  }

  private static ExpectedExecutionRequest parseExecutionRequest(byte[] bytes) throws IOException {
    if (bytes == null || bytes.length == 0 || bytes.length > MAX_REQUEST_BYTES) {
      throw new IllegalArgumentException("SDK_REQUEST_TOO_LARGE");
    }
    var value = parseStrictObject(bytes, "SDK_REQUEST_INVALID");
    if (!exactFields(
        value,
        "schema_version", "skill", "operation", "tenant_id", "project_id", "actor_id",
        "idempotency_key", "trace_id", "input"
    )) throw new IllegalArgumentException("SDK_REQUEST_INVALID");
    var skill = value.get("skill");
    var operation = value.get("operation");
    var tenantId = value.get("tenant_id");
    var projectId = value.get("project_id");
    var actorId = value.get("actor_id");
    var idempotencyKey = value.get("idempotency_key");
    var traceId = value.get("trace_id");
    if (!"1.0.0".equals(value.get("schema_version"))
        || !(skill instanceof String skillText) || !SKILL.matcher(skillText).matches()
        || !(operation instanceof String operationText) || !OPERATION.matcher(operationText).matches()
        || !(tenantId instanceof String tenantText) || !RESOURCE_ID.matcher(tenantText).matches()
        || !(projectId instanceof String projectText) || !RESOURCE_ID.matcher(projectText).matches()
        || !(actorId instanceof String actorText) || !ACTOR_ID.matcher(actorText).matches()
        || !boundedText(idempotencyKey, 200)
        || ((String) idempotencyKey).getBytes(StandardCharsets.UTF_8).length < 8
        || hasOuterWhitespace((String) idempotencyKey)
        || !boundedTraceId(traceId)
        || !(value.get("input") instanceof Map<?, ?>)) {
      throw new IllegalArgumentException("SDK_REQUEST_INVALID");
    }
    new RegisteredOperation((String) skill, (String) operation);
    @SuppressWarnings("unchecked")
    var input = (Map<String, Object>) value.get("input");
    validateOperationInput((String) skill, (String) operation, input);
    var canonicalBody = canonicalJson(value).getBytes(StandardCharsets.UTF_8);
    if (canonicalBody.length > MAX_REQUEST_BYTES) throw new IllegalArgumentException("SDK_REQUEST_TOO_LARGE");
    var digestDocument = new LinkedHashMap<String, Object>();
    digestDocument.put("execution_contract", "multimodal-intake-execution-v2");
    digestDocument.put("schema_version", "1.0.0");
    digestDocument.put("skill", skill);
    digestDocument.put("operation", operation);
    digestDocument.put("tenant_id", tenantId);
    digestDocument.put("project_id", projectId);
    digestDocument.put("actor_id", actorId);
    digestDocument.put("idempotency_key", idempotencyKey);
    digestDocument.put("input", value.get("input"));
    return new ExpectedExecutionRequest(
        (String) skill,
        (String) operation,
        (String) tenantId,
        (String) projectId,
        (String) actorId,
        (String) traceId,
        sha256(canonicalJson(digestDocument)),
        input,
        canonicalBody
    );
  }

  private static boolean safeVersion(Object value, boolean allowZero) {
    return value instanceof Long item
        && item >= (allowZero ? 0L : 1L)
        && item < MAX_SAFE_JSON_INTEGER;
  }

  private static boolean contentDigest(Object value) {
    return value instanceof String item && CONTENT_DIGEST.matcher(item).matches();
  }

  @SuppressWarnings("unchecked")
  private static void validateOperationInput(
      String skill, String operation, Map<String, Object> input
  ) {
    var contract = INPUT_FIELD_CONTRACTS.get(skill + "/" + operation);
    if (contract != null
        && (!contract.allowed().containsAll(input.keySet())
            || !input.keySet().containsAll(contract.required()))) {
      throw new IllegalArgumentException("OPERATION_INPUT_FIELDS_INVALID");
    }
    if ("elmos-multimodal-evaluation-framework".equals(skill) && "evaluate".equals(operation)) {
      if (!(input.get("subject") instanceof Map<?, ?> rawSubject)
          || !(input.get("evidence") instanceof List<?> evidence)
          || evidence.isEmpty() || evidence.size() > 240) {
        throw new IllegalArgumentException("OPERATION_INPUT_SHAPE_INVALID");
      }
      var subject = (Map<String, Object>) rawSubject;
      if (!exactFields(subject, "subject_id", "subject_kind", "artifact_digest", "implementation_version", "configuration_digest")
          || !boundedText(subject.get("subject_id"), 128)
          || !Set.of("parser", "provider", "model", "runtime", "configuration").contains(subject.get("subject_kind"))
          || !contentDigest(subject.get("artifact_digest"))
          || !boundedText(subject.get("implementation_version"), 128)
          || !contentDigest(subject.get("configuration_digest"))) {
        throw new IllegalArgumentException("OPERATION_INPUT_SHAPE_INVALID");
      }
      var caseIds = new HashSet<String>();
      for (var rawItem : evidence) {
        if (!(rawItem instanceof Map<?, ?> rawEvidence)) {
          throw new IllegalArgumentException("OPERATION_INPUT_SHAPE_INVALID");
        }
        var item = (Map<String, Object>) rawEvidence;
        if (!exactFields(item, "case_id", "media_type", "content_base64")
            || !boundedText(item.get("case_id"), 128)
            || !boundedText(item.get("media_type"), 256)
            || !boundedText(item.get("content_base64"), 16 * 1024 * 1024)
            || !caseIds.add((String) item.get("case_id"))) {
          throw new IllegalArgumentException("OPERATION_INPUT_SHAPE_INVALID");
        }
        try {
          Base64.getDecoder().decode((String) item.get("content_base64"));
        } catch (IllegalArgumentException error) {
          throw new IllegalArgumentException("OPERATION_INPUT_SHAPE_INVALID", error);
        }
      }
    }
    if ("elmos-folder-tree-input".equals(skill) && "append".equals(operation)) {
      var rawEntries = input.get("entries");
      if (!(rawEntries instanceof List<?> entries) || entries.isEmpty() || entries.size() > 1_000) {
        throw new IllegalArgumentException("OPERATION_INPUT_SHAPE_INVALID");
      }
      var allowed = Set.of("path", "kind", "byte_count", "content_digest", "role", "model_read_allowed", "metadata");
      for (var rawEntry : entries) {
        if (!(rawEntry instanceof Map<?, ?> entry)
            || !allowed.containsAll(entry.keySet())
            || !boundedText(entry.get("path"), 4096)
            || entry.get("content_digest") != null && !contentDigest(entry.get("content_digest"))) {
          throw new IllegalArgumentException("OPERATION_INPUT_SHAPE_INVALID");
        }
      }
    }
    if ("elmos-resumable-multi-file-folder-upload".equals(skill) && "confirm_part".equals(operation)) {
      var rawData = input.get("data_base64");
      var byteCount = input.get("byte_count");
      var partNumber = input.get("part_number");
      if (!(rawData instanceof String encoded)
          || !(byteCount instanceof Long expectedBytes) || expectedBytes < 0
          || !(partNumber instanceof Long part) || part < 1
          || !contentDigest(input.get("part_digest"))) {
        throw new IllegalArgumentException("OPERATION_INPUT_SHAPE_INVALID");
      }
      final byte[] decoded;
      try {
        decoded = Base64.getDecoder().decode(encoded);
      } catch (IllegalArgumentException error) {
        throw new IllegalArgumentException("OPERATION_INPUT_SHAPE_INVALID", error);
      }
      if (decoded.length != expectedBytes
          || !("sha256:" + sha256Bytes(decoded)).equals(input.get("part_digest"))) {
        throw new IllegalArgumentException("OPERATION_INPUT_SHAPE_INVALID");
      }
    }
    if ("elmos-downstream-agent-integration".equals(skill)) {
      var idFields = Map.of(
          "build_context", List.of("task_id", "subject_id"),
          "get_context", List.of("context_id"),
          "get_grant", List.of("context_id", "grant_id"),
          "revoke_grant", List.of("context_id", "grant_id"),
          "link_result", List.of("context_id", "grant_id", "result_receipt_id"),
          "list_result_links", List.of("context_id")
      ).get(operation);
      if (idFields == null || idFields.stream().anyMatch(
          field -> !(input.get(field) instanceof String value) || !RESOURCE_ID.matcher(value).matches()
      )) throw new IllegalArgumentException("OPERATION_INPUT_SHAPE_INVALID");
      if ("build_context".equals(operation)) {
        if (!(input.get("package_version") instanceof Long version) || version < 1) {
          throw new IllegalArgumentException("OPERATION_INPUT_SHAPE_INVALID");
        }
        for (var field : List.of("source_receipt_ids", "tool_receipt_ids")) {
          var rawValues = input.getOrDefault(field, List.of());
          if (!(rawValues instanceof List<?> values)
              || "source_receipt_ids".equals(field) && values.isEmpty()
              || values.size() > 256
              || values.stream().anyMatch(value -> !(value instanceof String item) || !RESOURCE_ID.matcher(item).matches())
              || new HashSet<>(values).size() != values.size()) {
            throw new IllegalArgumentException("OPERATION_INPUT_SHAPE_INVALID");
          }
        }
      }
      if ("revoke_grant".equals(operation) && !boundedText(input.get("reason"), 512)) {
        throw new IllegalArgumentException("OPERATION_INPUT_SHAPE_INVALID");
      }
    }
  }

  private static String sha256Bytes(byte[] value) {
    try {
      var digest = MessageDigest.getInstance("SHA-256").digest(value);
      var result = new StringBuilder(64);
      for (var item : digest) result.append(String.format("%02x", item & 0xff));
      return result.toString();
    } catch (NoSuchAlgorithmException error) {
      throw new IllegalStateException(error);
    }
  }

  @SuppressWarnings("unchecked")
  private static Map<String, Object> humanReviewSourceRef(Object raw) throws IOException {
    if (!(raw instanceof Map<?, ?>)
        || !((Map<String, Object>) raw).keySet().equals(HUMAN_REVIEW_SOURCE_REF_V2_FIELDS)) {
      throw new IOException("SDK_HUMAN_REVIEW_SOURCE_REF_INVALID");
    }
    var value = (Map<String, Object>) raw;
    var digestFields = Set.of(
        "content_digest", "asset_sha256", "target_digest", "snapshot_digest",
        "head_value_digest", "source_digest", "provenance_digest", "original_value_client_digest"
    );
    if (!"human-review-source-ref-v2".equals(value.get("schema_version"))
        || !(value.get("content_id") instanceof String contentId) || !RESOURCE_ID.matcher(contentId).matches()
        || !safeVersion(value.get("content_version"), false)
        || !(value.get("target_kind") instanceof String targetKind)
        || !Set.of("TEXT", "SPEAKER", "TIME_RANGE", "BBOX", "TABLE", "REQUIREMENT", "CONFLICT").contains(targetKind)
        || !(value.get("snapshot_id") instanceof String snapshotId) || !RESOURCE_ID.matcher(snapshotId).matches()
        || !safeVersion(value.get("head_version"), false)
        || !HUMAN_REVIEW_ORIGINAL_VALUE_DIGEST_CONTRACT.equals(value.get("original_value_digest_contract"))
        || digestFields.stream().anyMatch(field -> !contentDigest(value.get(field)))) {
      throw new IOException("SDK_HUMAN_REVIEW_SOURCE_REF_INVALID");
    }
    return value;
  }

  @SuppressWarnings("unchecked")
  private static Map<String, Object> humanReviewSource(
      Object raw,
      boolean detail,
      Map<String, Object> expectedInput
  ) throws IOException {
    var expectedFields = detail
        ? HUMAN_REVIEW_SOURCE_DETAIL_FIELDS
        : HUMAN_REVIEW_SOURCE_SUMMARY_FIELDS;
    if (!(raw instanceof Map<?, ?>)
        || !((Map<String, Object>) raw).keySet().equals(expectedFields)) {
      throw new IOException("SDK_HUMAN_REVIEW_SOURCE_CONTRACT_INVALID");
    }
    var value = (Map<String, Object>) raw;
    var sourceRef = humanReviewSourceRef(value.get("source_ref"));
    var confidence = value.get("confidence");
    if (!(detail ? "human-review-source-detail-v1" : "human-review-source-summary-v1")
            .equals(value.get("schema_version"))
        || !Objects.equals(value.get("content_id"), expectedInput.get("content_id"))
        || !Objects.equals(value.get("content_version"), expectedInput.get("expected_asset_version"))
        || !(value.get("target_kind") instanceof String targetKind)
        || !Set.of("TEXT", "SPEAKER", "TIME_RANGE", "BBOX", "TABLE", "REQUIREMENT", "CONFLICT").contains(targetKind)
        || !(value.get("target") instanceof Map<?, ?>)
        || !contentDigest(value.get("target_digest"))
        || !(confidence instanceof Number confidenceNumber)
        || !Double.isFinite(confidenceNumber.doubleValue())
        || confidenceNumber.doubleValue() < 0 || confidenceNumber.doubleValue() > 1
        || !safeVersion(value.get("head_version"), false)
        || !Set.of("SNAPSHOT", "APPLY", "REVERT").contains(value.get("head_direction"))
        || !safeVersion(value.get("head_correction_version"), true)
        || !contentDigest(value.get("original_value_client_digest"))
        || !HUMAN_REVIEW_ORIGINAL_VALUE_DIGEST_CONTRACT.equals(value.get("original_value_digest_contract"))
        || !Objects.equals(sourceRef.get("content_id"), value.get("content_id"))
        || !Objects.equals(sourceRef.get("content_version"), value.get("content_version"))
        || !Objects.equals(sourceRef.get("target_kind"), value.get("target_kind"))
        || !Objects.equals(sourceRef.get("target_digest"), value.get("target_digest"))
        || !Objects.equals(sourceRef.get("head_version"), value.get("head_version"))
        || !Objects.equals(sourceRef.get("original_value_client_digest"), value.get("original_value_client_digest"))
        || !Objects.equals(sourceRef.get("original_value_digest_contract"), value.get("original_value_digest_contract"))) {
      throw new IOException("SDK_HUMAN_REVIEW_SOURCE_CONTRACT_INVALID");
    }
    if (detail) {
      var digest = "sha256:" + sha256(canonicalJson(value.get("original_value")));
      if (!MessageDigest.isEqual(
          digest.getBytes(StandardCharsets.US_ASCII),
          ((String) value.get("original_value_client_digest")).getBytes(StandardCharsets.US_ASCII)
      )) throw new IOException("SDK_HUMAN_REVIEW_SOURCE_DIGEST_INVALID");
    }
    return value;
  }

  @SuppressWarnings("unchecked")
  private static Map<String, Object> humanReviewSourceCursor(
      Object raw,
      ExpectedExecutionRequest expected
  ) throws IOException {
    if (!(raw instanceof String value)
        || value.isEmpty() || value.length() > 4_096
        || value.indexOf('=') >= 0 || !value.matches("[A-Za-z0-9_-]+")) {
      throw new IOException("SDK_HUMAN_REVIEW_SOURCE_CURSOR_INVALID");
    }
    final byte[] bytes;
    final String rawJson;
    final Object parsed;
    try {
      bytes = Base64.getUrlDecoder().decode(
          value + "=".repeat((4 - value.length() % 4) % 4)
      );
      if (!Base64.getUrlEncoder().withoutPadding().encodeToString(bytes).equals(value)) {
        throw new IOException("non-canonical base64url");
      }
      rawJson = strictUtf8(bytes, "SDK_HUMAN_REVIEW_SOURCE_CURSOR_INVALID");
      parsed = new StrictJsonParser(rawJson).parse();
    } catch (IllegalArgumentException error) {
      throw new IOException("SDK_HUMAN_REVIEW_SOURCE_CURSOR_INVALID", error);
    }
    if (!(parsed instanceof Map<?, ?>)
        || !canonicalJson(parsed).equals(rawJson)) {
      throw new IOException("SDK_HUMAN_REVIEW_SOURCE_CURSOR_INVALID");
    }
    var cursor = (Map<String, Object>) parsed;
    if (!exactFields(
        cursor,
        "version", "filter_digest", "collection_digest", "collection_generation",
        "target_kind", "target_digest"
    )) throw new IOException("SDK_HUMAN_REVIEW_SOURCE_CURSOR_INVALID");
    var kindsRaw = expected.input().get("kinds");
    if (!(expected.input().get("content_id") instanceof String contentId)
        || !RESOURCE_ID.matcher(contentId).matches()
        || !safeVersion(expected.input().get("expected_asset_version"), false)
        || !(kindsRaw instanceof List<?> kinds)) {
      throw new IOException("SDK_HUMAN_REVIEW_SOURCE_CURSOR_INVALID");
    }
    String previousKind = null;
    for (var item : kinds) {
      if (!(item instanceof String kind)
          || !Set.of("TEXT", "SPEAKER", "TIME_RANGE", "BBOX", "TABLE", "REQUIREMENT", "CONFLICT").contains(kind)
          || previousKind != null && previousKind.compareTo(kind) >= 0) {
        throw new IOException("SDK_HUMAN_REVIEW_SOURCE_CURSOR_INVALID");
      }
      previousKind = kind;
    }
    var filter = new LinkedHashMap<String, Object>();
    filter.put("schema_version", "human-review-source-filter-v1");
    filter.put("tenant_id", expected.tenantId());
    filter.put("project_id", expected.projectId());
    filter.put("content_id", contentId);
    filter.put("content_version", expected.input().get("expected_asset_version"));
    filter.put("kinds", kinds);
    var filterDigest = sha256(canonicalJson(filter));
    if (!"human-review-source-cursor-v1".equals(cursor.get("version"))
        || !(cursor.get("filter_digest") instanceof String observedFilter)
        || !DIGEST.matcher(observedFilter).matches()
        || !MessageDigest.isEqual(
            observedFilter.getBytes(StandardCharsets.US_ASCII),
            filterDigest.getBytes(StandardCharsets.US_ASCII)
        )
        || !(cursor.get("collection_digest") instanceof String collectionDigest)
        || !DIGEST.matcher(collectionDigest).matches()
        || !safeVersion(cursor.get("collection_generation"), false)
        || !Set.of("TEXT", "SPEAKER", "TIME_RANGE", "BBOX", "TABLE", "REQUIREMENT", "CONFLICT")
            .contains(cursor.get("target_kind"))
        || !contentDigest(cursor.get("target_digest"))) {
      throw new IOException("SDK_HUMAN_REVIEW_SOURCE_CURSOR_INVALID");
    }
    return cursor;
  }

  @SuppressWarnings("unchecked")
  private static Map<String, Object> humanReviewTask(
      Object raw,
      ExpectedExecutionRequest expected
  ) throws IOException {
    return humanReviewTask(raw, expected, expected.input());
  }

  @SuppressWarnings("unchecked")
  private static Map<String, Object> humanReviewTask(
      Object raw,
      ExpectedExecutionRequest expected,
      Map<String, Object> expectedInput
  ) throws IOException {
    var taskFields = Set.of(
        "task_id", "tenant_id", "project_id", "asset_id", "target_kind", "target",
        "original_value", "source_digest", "source_ref", "confidence", "reason", "state",
        "current_correction_version", "current_correction_digest", "effective_version",
        "effective_digest", "claim_actor_id", "claim_fence", "claim_expires_at", "version",
        "created_by", "created_at", "updated_at", "closed_at"
    );
    if (!(raw instanceof Map<?, ?>) || !((Map<String, Object>) raw).keySet().equals(taskFields)) {
      throw new IOException("SDK_HUMAN_REVIEW_TASK_CONTRACT_INVALID");
    }
    var value = (Map<String, Object>) raw;
    var sourceRef = humanReviewSourceRef(value.get("source_ref"));
    var confidence = value.get("confidence");
    var claimActor = value.get("claim_actor_id");
    if (!(value.get("task_id") instanceof String taskId) || !RESOURCE_ID.matcher(taskId).matches()
        || !expected.tenantId().equals(value.get("tenant_id"))
        || !expected.projectId().equals(value.get("project_id"))
        || !Objects.equals(value.get("asset_id"), expectedInput.get("content_id"))
        || !Objects.equals(value.get("target_kind"), expectedInput.get("target_kind"))
        || !(value.get("target") instanceof Map<?, ?>)
        || !contentDigest(value.get("source_digest"))
        || !Objects.equals(value.get("source_digest"), sourceRef.get("source_digest"))
        || !Objects.equals(sourceRef.get("content_id"), value.get("asset_id"))
        || !Objects.equals(sourceRef.get("content_version"), expectedInput.get("expected_asset_version"))
        || !Objects.equals(sourceRef.get("target_kind"), value.get("target_kind"))
        || !Objects.equals(sourceRef.get("target_digest"), expectedInput.get("target_digest"))
        || !Objects.equals(sourceRef.get("snapshot_id"), expectedInput.get("expected_snapshot_id"))
        || !Objects.equals(sourceRef.get("snapshot_digest"), expectedInput.get("expected_snapshot_digest"))
        || !Objects.equals(sourceRef.get("head_version"), expectedInput.get("expected_head_version"))
        || !Objects.equals(sourceRef.get("head_value_digest"), expectedInput.get("expected_head_value_digest"))
        || !Objects.equals(sourceRef.get("original_value_client_digest"), expectedInput.get("original_value_digest"))
        || !(confidence instanceof Number confidenceNumber)
        || !Double.isFinite(confidenceNumber.doubleValue())
        || confidenceNumber.doubleValue() < 0 || confidenceNumber.doubleValue() > 1
        || !boundedText(value.get("reason"), 2_000)
        || !Objects.equals(value.get("reason"), expectedInput.get("reason"))
        || !Set.of("QUEUED", "CLAIMED", "EDITED", "APPROVED", "REJECTED", "REOPENED", "REVERTING", "REVERTED")
            .contains(value.get("state"))
        || !safeVersion(value.get("current_correction_version"), true)
        || value.get("current_correction_digest") != null && !contentDigest(value.get("current_correction_digest"))
        || !safeVersion(value.get("effective_version"), true)
        || value.get("effective_digest") != null && !contentDigest(value.get("effective_digest"))
        || claimActor != null && (!(claimActor instanceof String actor) || !ACTOR_ID.matcher(actor).matches())
        || !safeVersion(value.get("claim_fence"), true)
        || value.get("claim_expires_at") != null && !timestamp(value.get("claim_expires_at"))
        || !safeVersion(value.get("version"), false)
        || !expected.actorId().equals(value.get("created_by"))
        || !timestamp(value.get("created_at"))
        || !timestamp(value.get("updated_at"))
        || value.get("closed_at") != null && !timestamp(value.get("closed_at"))) {
      throw new IOException("SDK_HUMAN_REVIEW_TASK_CONTRACT_INVALID");
    }
    var digest = "sha256:" + sha256(canonicalJson(value.get("original_value")));
    if (!MessageDigest.isEqual(
        digest.getBytes(StandardCharsets.US_ASCII),
        ((String) sourceRef.get("original_value_client_digest")).getBytes(StandardCharsets.US_ASCII)
    )) throw new IOException("SDK_HUMAN_REVIEW_TASK_DIGEST_INVALID");
    return value;
  }

  @SuppressWarnings("unchecked")
  private static Map<String, Object> humanReviewEnqueueInput(Object raw) throws IOException {
    if (!(raw instanceof Map<?, ?>)
        || !((Map<String, Object>) raw).keySet().equals(HUMAN_REVIEW_SOURCE_BOUND_ENQUEUE_FIELDS)) {
      throw new IOException("SDK_HUMAN_REVIEW_ENQUEUE_INPUT_INVALID");
    }
    var value = (Map<String, Object>) raw;
    if (!(value.get("content_id") instanceof String contentId) || !RESOURCE_ID.matcher(contentId).matches()
        || !safeVersion(value.get("expected_asset_version"), false)
        || !Set.of("TEXT", "SPEAKER", "TIME_RANGE", "BBOX", "TABLE", "REQUIREMENT", "CONFLICT")
            .contains(value.get("target_kind"))
        || !contentDigest(value.get("target_digest"))
        || !safeVersion(value.get("expected_head_version"), false)
        || !(value.get("expected_snapshot_id") instanceof String snapshotId)
        || !RESOURCE_ID.matcher(snapshotId).matches()
        || !contentDigest(value.get("expected_snapshot_digest"))
        || !contentDigest(value.get("expected_head_value_digest"))
        || !contentDigest(value.get("original_value_digest"))
        || !boundedText(value.get("reason"), 2_000)) {
      throw new IOException("SDK_HUMAN_REVIEW_ENQUEUE_INPUT_INVALID");
    }
    return value;
  }

  @SuppressWarnings("unchecked")
  private static ValidatedPreparation humanReviewPreparation(
      Object raw,
      ExpectedExecutionRequest expected,
      Set<String> allowedStates
  ) throws IOException {
    if (!(raw instanceof Map<?, ?>)
        || !((Map<String, Object>) raw).keySet().equals(HUMAN_REVIEW_ENQUEUE_PREPARATION_FIELDS)) {
      throw new IOException("SDK_HUMAN_REVIEW_PREPARATION_CONTRACT_INVALID");
    }
    var value = (Map<String, Object>) raw;
    var handle = value.get("recovery_handle");
    var state = value.get("state");
    if (!"human-review-enqueue-preparation-v1".equals(value.get("schema_version"))
        || !Objects.equals(handle, expected.input().get("recovery_handle"))
        || !(handle instanceof String handleText)
        || handleText.getBytes(StandardCharsets.UTF_8).length < 32
        || handleText.getBytes(StandardCharsets.UTF_8).length > 200
        || !contentDigest(value.get("request_digest"))
        || !(state instanceof String stateText) || !allowedStates.contains(stateText)
        || !(value.get("safe_to_clear") instanceof Boolean)
        || !timestamp(value.get("expires_at")) || !timestamp(value.get("prepared_at"))
        || value.get("executed_at") != null && !timestamp(value.get("executed_at"))
        || value.get("task_id") != null
        && (!(value.get("task_id") instanceof String taskId) || !RESOURCE_ID.matcher(taskId).matches())) {
      throw new IOException("SDK_HUMAN_REVIEW_PREPARATION_CONTRACT_INVALID");
    }
    var enqueueInput = humanReviewEnqueueInput(value.get("enqueue_input"));
    if (HUMAN_REVIEW_ENQUEUE_PREPARE_OPERATION.equals(expected.operation().replace('-', '_'))
        && enqueueInput.entrySet().stream()
            .anyMatch(entry -> !Objects.equals(expected.input().get(entry.getKey()), entry.getValue()))) {
      throw new IOException("SDK_HUMAN_REVIEW_PREPARATION_BINDING_INVALID");
    }
    var digest = "sha256:" + sha256(canonicalJson(enqueueInput));
    if (!MessageDigest.isEqual(
        digest.getBytes(StandardCharsets.US_ASCII),
        ((String) value.get("request_digest")).getBytes(StandardCharsets.US_ASCII)
    )) throw new IOException("SDK_HUMAN_REVIEW_PREPARATION_DIGEST_INVALID");
    if ("PREPARED".equals(state)
        && (!Boolean.FALSE.equals(value.get("safe_to_clear"))
            || value.get("executed_at") != null || value.get("task_id") != null)
        || "EXECUTED".equals(state)
        && (!Boolean.TRUE.equals(value.get("safe_to_clear"))
            || value.get("executed_at") == null || value.get("task_id") == null)
        || "EXPIRED".equals(state)
        && (!Boolean.TRUE.equals(value.get("safe_to_clear"))
            || value.get("executed_at") != null || value.get("task_id") != null)) {
      throw new IOException("SDK_HUMAN_REVIEW_PREPARATION_CONTRACT_INVALID");
    }
    return new ValidatedPreparation(value, enqueueInput);
  }

  @SuppressWarnings("unchecked")
  private static Map<String, Object> humanReviewPreparationAbsence(
      Object raw,
      ExpectedExecutionRequest expected
  ) throws IOException {
    if (!(raw instanceof Map<?, ?>)
        || !((Map<String, Object>) raw).keySet().equals(HUMAN_REVIEW_ENQUEUE_PREPARATION_ABSENCE_FIELDS)) {
      throw new IOException("SDK_HUMAN_REVIEW_PREPARATION_CONTRACT_INVALID");
    }
    var value = (Map<String, Object>) raw;
    if (!"human-review-enqueue-preparation-absence-v1".equals(value.get("schema_version"))
        || !Objects.equals(value.get("recovery_handle"), expected.input().get("recovery_handle"))
        || !"ABSENT".equals(value.get("state"))
        || !Boolean.TRUE.equals(value.get("safe_to_clear"))) {
      throw new IOException("SDK_HUMAN_REVIEW_PREPARATION_CONTRACT_INVALID");
    }
    return value;
  }

  @SuppressWarnings("unchecked")
  private static void validateHumanReviewExecutionOutput(
      Map<String, Object> output,
      ExpectedExecutionRequest expected,
      Object resultCode
  ) throws IOException {
    var metadata = Set.of("handler_id", "phase", "metrics");
    if (!"execute_human_review_and_correction".equals(output.get("handler_id"))
        || !"review".equals(output.get("phase"))
        || !(output.get("metrics") instanceof Map<?, ?> metrics) || !metrics.isEmpty()) {
      throw new IOException("SDK_HUMAN_REVIEW_OUTPUT_CONTRACT_INVALID");
    }
    var operation = expected.operation().replace('-', '_');
    if (HUMAN_REVIEW_SOURCE_LIST_OPERATION.equals(operation)) {
      if (!"HUMAN_REVIEW_SOURCES_LISTED".equals(resultCode)) {
        throw new IOException("SDK_HUMAN_REVIEW_OUTPUT_CODE_INVALID");
      }
      var fields = new HashSet<>(metadata);
      fields.addAll(Set.of("sources", "next_cursor", "total"));
      if (!expected.input().keySet().equals(
              Set.of("content_id", "expected_asset_version", "kinds", "limit", "cursor")
          )
          || !output.keySet().equals(fields)
          || !(output.get("sources") instanceof List<?> sources)
          || !(expected.input().get("content_id") instanceof String contentId)
          || !RESOURCE_ID.matcher(contentId).matches()
          || !safeVersion(expected.input().get("expected_asset_version"), false)
          || !(expected.input().get("kinds") instanceof List<?>)
          || !safeVersion(output.get("total"), true)
          || (Long) output.get("total") > HUMAN_REVIEW_SOURCE_COLLECTION_MAX_ITEMS
          || (Long) output.get("total") < sources.size()
          || !safeVersion(expected.input().get("limit"), false)
          || (Long) expected.input().get("limit") > HUMAN_REVIEW_SOURCE_LIST_MAX_ITEMS
          || sources.size() > Math.min((Long) expected.input().get("limit"), HUMAN_REVIEW_SOURCE_LIST_MAX_ITEMS)
          || expected.input().get("cursor") != null
          && !(expected.input().get("cursor") instanceof String)) {
        throw new IOException("SDK_HUMAN_REVIEW_OUTPUT_CONTRACT_INVALID");
      }
      var inputCursor = expected.input().get("cursor");
      var priorCursor = inputCursor == null
          ? null
          : humanReviewSourceCursor(inputCursor, expected);
      var validatedSources = new ArrayList<Map<String, Object>>();
      var pairs = new ArrayList<String>();
      for (var source : sources) {
        var validated = humanReviewSource(source, false, expected.input());
        validatedSources.add(validated);
        pairs.add(validated.get("target_kind") + "\0" + validated.get("target_digest"));
      }
      var sortedPairs = new ArrayList<>(new HashSet<>(pairs));
      Collections.sort(sortedPairs);
      var kinds = (List<?>) expected.input().get("kinds");
      String previousKind = null;
      for (var rawKind : kinds) {
        if (!(rawKind instanceof String kind)
            || !Set.of("TEXT", "SPEAKER", "TIME_RANGE", "BBOX", "TABLE", "REQUIREMENT", "CONFLICT").contains(kind)
            || previousKind != null && previousKind.compareTo(kind) >= 0) {
          throw new IOException("SDK_HUMAN_REVIEW_OUTPUT_CONTRACT_INVALID");
        }
        previousKind = kind;
      }
      if (!pairs.equals(sortedPairs)
          || !kinds.isEmpty() && validatedSources.stream()
              .anyMatch(source -> !kinds.contains(source.get("target_kind")))
          || priorCursor != null && !pairs.isEmpty()
          && pairs.get(0).compareTo(
              priorCursor.get("target_kind") + "\0" + priorCursor.get("target_digest")
          ) <= 0) {
        throw new IOException("SDK_HUMAN_REVIEW_OUTPUT_CONTRACT_INVALID");
      }
      if (output.get("next_cursor") == null) {
        if (inputCursor == null && (Long) output.get("total") != validatedSources.size()
            || inputCursor != null && (Long) output.get("total") <= validatedSources.size()) {
          throw new IOException("SDK_HUMAN_REVIEW_OUTPUT_CONTRACT_INVALID");
        }
      } else {
        var nextCursor = humanReviewSourceCursor(output.get("next_cursor"), expected);
        var nextPair = nextCursor.get("target_kind") + "\0" + nextCursor.get("target_digest");
        if (validatedSources.size() != (Long) expected.input().get("limit")
            || (Long) output.get("total") <= validatedSources.size()
            || pairs.isEmpty() || !nextPair.equals(pairs.get(pairs.size() - 1))
            || priorCursor != null
            && (!Objects.equals(nextCursor.get("collection_digest"), priorCursor.get("collection_digest"))
                || !Objects.equals(nextCursor.get("collection_generation"), priorCursor.get("collection_generation")))) {
          throw new IOException("SDK_HUMAN_REVIEW_OUTPUT_CONTRACT_INVALID");
        }
      }
      return;
    }
    if (HUMAN_REVIEW_SOURCE_GET_OPERATION.equals(operation)) {
      if (!"HUMAN_REVIEW_SOURCE_RETRIEVED".equals(resultCode)) {
        throw new IOException("SDK_HUMAN_REVIEW_OUTPUT_CODE_INVALID");
      }
      var fields = new HashSet<>(metadata);
      fields.add("source");
      if (!expected.input().keySet().equals(Set.of(
              "content_id", "expected_asset_version", "target_kind", "target_digest",
              "expected_head_version"
          )) || !output.keySet().equals(fields)) {
        throw new IOException("SDK_HUMAN_REVIEW_OUTPUT_CONTRACT_INVALID");
      }
      var source = humanReviewSource(output.get("source"), true, expected.input());
      if (!Objects.equals(source.get("target_kind"), expected.input().get("target_kind"))
          || !Objects.equals(source.get("target_digest"), expected.input().get("target_digest"))
          || !Objects.equals(source.get("head_version"), expected.input().get("expected_head_version"))) {
        throw new IOException("SDK_HUMAN_REVIEW_SOURCE_BINDING_INVALID");
      }
      return;
    }
    if (HUMAN_REVIEW_SOURCE_BOUND_ENQUEUE_OPERATION.equals(operation)) {
      if (!"HUMAN_REVIEW_TASK_ENQUEUED".equals(resultCode)) {
        throw new IOException("SDK_HUMAN_REVIEW_OUTPUT_CODE_INVALID");
      }
      var fields = new HashSet<>(metadata);
      fields.add("task");
      if (!output.keySet().equals(fields)) {
        throw new IOException("SDK_HUMAN_REVIEW_OUTPUT_CONTRACT_INVALID");
      }
      humanReviewEnqueueInput(expected.input());
      humanReviewTask(output.get("task"), expected);
      return;
    }
    if (HUMAN_REVIEW_ENQUEUE_PREPARE_OPERATION.equals(operation)) {
      var fields = new HashSet<>(metadata);
      fields.add("preparation");
      if (!"HUMAN_REVIEW_ENQUEUE_PREPARED".equals(resultCode)
          || !expected.input().keySet().equals(HUMAN_REVIEW_ENQUEUE_PREPARE_FIELDS)
          || !boundedText(expected.input().get("execute_idempotency_key"), 200)
          || ((String) expected.input().get("execute_idempotency_key"))
              .getBytes(StandardCharsets.UTF_8).length < 8
          || !output.keySet().equals(fields)) {
        throw new IOException("SDK_HUMAN_REVIEW_OUTPUT_CONTRACT_INVALID");
      }
      humanReviewPreparation(output.get("preparation"), expected, Set.of("PREPARED"));
      return;
    }
    if (HUMAN_REVIEW_ENQUEUE_EXECUTE_OPERATION.equals(operation)) {
      if (!expected.input().keySet().equals(HUMAN_REVIEW_ENQUEUE_EXECUTE_FIELDS)
          || !boundedText(expected.input().get("recovery_handle"), 200)
          || ((String) expected.input().get("recovery_handle"))
              .getBytes(StandardCharsets.UTF_8).length < 32) {
        throw new IOException("SDK_HUMAN_REVIEW_OUTPUT_CONTRACT_INVALID");
      }
      var terminalFields = new HashSet<>(metadata);
      terminalFields.add("preparation");
      if ("HUMAN_REVIEW_ENQUEUE_PREPARATION_ABSENT".equals(resultCode)) {
        if (!output.keySet().equals(terminalFields)) {
          throw new IOException("SDK_HUMAN_REVIEW_OUTPUT_CONTRACT_INVALID");
        }
        humanReviewPreparationAbsence(output.get("preparation"), expected);
        return;
      }
      if ("HUMAN_REVIEW_ENQUEUE_PREPARATION_EXPIRED".equals(resultCode)) {
        if (!output.keySet().equals(terminalFields)) {
          throw new IOException("SDK_HUMAN_REVIEW_OUTPUT_CONTRACT_INVALID");
        }
        humanReviewPreparation(output.get("preparation"), expected, Set.of("EXPIRED"));
        return;
      }
      if ("HUMAN_REVIEW_TASK_ENQUEUED_FROM_PREPARATION".equals(resultCode)) {
        var completedFields = new HashSet<>(terminalFields);
        completedFields.add("task");
        if (!output.keySet().equals(completedFields)) {
          throw new IOException("SDK_HUMAN_REVIEW_OUTPUT_CONTRACT_INVALID");
        }
        var preparation = humanReviewPreparation(
            output.get("preparation"), expected, Set.of("EXECUTED")
        );
        var task = humanReviewTask(output.get("task"), expected, preparation.enqueueInput());
        if (!Objects.equals(preparation.preparation().get("task_id"), task.get("task_id"))) {
          throw new IOException("SDK_HUMAN_REVIEW_PREPARATION_BINDING_INVALID");
        }
        return;
      }
      throw new IOException("SDK_HUMAN_REVIEW_OUTPUT_CODE_INVALID");
    }
  }

  private static Map<String, Object> validateExecutionResult(
      Map<String, Object> value,
      ExpectedExecutionRequest expected
  ) throws IOException {
    var required = exactFields(
        value,
        "schema_version", "skill", "operation", "status", "retryable", "trace_id",
        "request_digest", "implementation_state", "external_evidence", "certification",
        "output", "result_digest"
    );
    var withCode = exactFields(
        value,
        "schema_version", "skill", "operation", "status", "retryable", "trace_id",
        "request_digest", "implementation_state", "external_evidence", "certification",
        "output", "code", "result_digest"
    );
    var skill = value.get("skill");
    var operation = value.get("operation");
    var status = value.get("status");
    var code = value.get("code");
    var resultDigest = value.get("result_digest");
    if (!(required || withCode)
        || !"1.0.0".equals(value.get("schema_version"))
        || !(skill instanceof String skillText) || !SKILL.matcher(skillText).matches()
        || !(operation instanceof String operationText) || !OPERATION.matcher(operationText).matches()
        || !(status instanceof String statusText) || !EXECUTION_STATES.contains(statusText)
        || !(value.get("retryable") instanceof Boolean)
        || !boundedTraceId(value.get("trace_id"))
        || !(value.get("request_digest") instanceof String requestDigest)
        || !DIGEST.matcher(requestDigest).matches()
        || !Set.of("CODE_IMPLEMENTED_LOCAL", "BRIDGE_REQUIRED").contains(value.get("implementation_state"))
        || !"NOT_RUN".equals(value.get("external_evidence"))
        || !"NOT_CERTIFIED".equals(value.get("certification"))
        || !(value.get("output") instanceof Map<?, ?>)
        || Set.of("BLOCKED", "FAILED").contains(status) && !withCode
        || withCode && (!(code instanceof String codeText) || !PUBLIC_CODE.matcher(codeText).matches())
        || !(resultDigest instanceof String digestText) || !DIGEST.matcher(digestText).matches()) {
      throw new IOException("SDK_RESPONSE_CONTRACT_INVALID");
    }
    if (!expected.skill().equals(skill)
        || !expected.operation().equals(operation)
        || !expected.traceId().equals(value.get("trace_id"))
        || !expected.requestDigest().equals(value.get("request_digest"))) {
      throw new IOException("SDK_RESPONSE_REQUEST_BINDING_INVALID");
    }
    @SuppressWarnings("unchecked")
    var output = (Map<String, Object>) value.get("output");
    if (expected.skill().equals("elmos-multimodal-input-orchestrator")
        && expected.operation().replace('-', '_').equals("bootstrap_project")
        && status.equals("SUCCEEDED")
        && !expected.projectId().equals(output.get("project_id"))) {
      throw new IOException("SDK_RESPONSE_PROJECT_BINDING_INVALID");
    }
    if (expected.skill().equals(HUMAN_REVIEW_SKILL)
        && status.equals("SUCCEEDED")
        && Set.of(
            HUMAN_REVIEW_SOURCE_LIST_OPERATION,
            HUMAN_REVIEW_SOURCE_GET_OPERATION,
            HUMAN_REVIEW_SOURCE_BOUND_ENQUEUE_OPERATION,
            HUMAN_REVIEW_ENQUEUE_PREPARE_OPERATION,
            HUMAN_REVIEW_ENQUEUE_EXECUTE_OPERATION
        ).contains(expected.operation().replace('-', '_'))) {
      validateHumanReviewExecutionOutput(output, expected, value.get("code"));
    }
    var unsigned = new LinkedHashMap<>(value);
    unsigned.remove("result_digest");
    var calculated = sha256(canonicalJson(unsigned));
    if (!MessageDigest.isEqual(
        ((String) resultDigest).getBytes(StandardCharsets.US_ASCII),
        calculated.getBytes(StandardCharsets.US_ASCII)
    )) throw new IOException("SDK_RESPONSE_DIGEST_INVALID");
    return value;
  }

  @SuppressWarnings("unchecked")
  private static Map<String, Object> validateCapabilityResponse(Map<String, Object> value)
      throws IOException {
    if (!exactFields(
        value,
        "schema_version", "status", "skill_count", "skills", "external_evidence", "certification"
    )
        || !"1.0.0".equals(value.get("schema_version"))
        || !"CODE_IMPLEMENTED_LOCAL".equals(value.get("status"))
        || !Long.valueOf(50).equals(value.get("skill_count"))
        || !(value.get("skills") instanceof List<?> rawSkills) || rawSkills.size() != 50
        || !"NOT_RUN".equals(value.get("external_evidence"))
        || !"NOT_CERTIFIED".equals(value.get("certification"))) {
      throw new IOException("SDK_CAPABILITIES_CONTRACT_INVALID");
    }
    var ordinals = new HashSet<Long>();
    var names = new HashSet<String>();
    for (var rawItem : rawSkills) {
      if (!(rawItem instanceof Map<?, ?> rawMap)) throw new IOException("SDK_CAPABILITIES_CONTRACT_INVALID");
      var item = (Map<String, Object>) rawMap;
      var ordinal = item.get("ordinal");
      var skill = item.get("skill");
      var handler = item.get("handler_id");
      var phase = item.get("phase");
      var rawTransport = item.get("transport");
      if (!(rawTransport instanceof Map<?, ?> transportMap)) {
        throw new IOException("SDK_CAPABILITIES_CONTRACT_INVALID");
      }
      var transport = (Map<String, Object>) transportMap;
      if (!exactFields(
          item,
          "ordinal", "skill", "handler_id", "phase", "implementation_state",
          "external_evidence", "certification", "transport"
      )
          || !(ordinal instanceof Long ordinalValue) || ordinalValue < 1 || ordinalValue > 50
          || !ordinals.add(ordinalValue)
          || !(skill instanceof String skillText) || !SKILL.matcher(skillText).matches()
          || !names.add(skillText)
          || !(handler instanceof String handlerText) || !HANDLER.matcher(handlerText).matches()
          || !(phase instanceof String phaseText) || !CAPABILITY_PHASES.contains(phaseText)
          || !"CODE_IMPLEMENTED_LOCAL".equals(item.get("implementation_state"))
          || !"NOT_RUN".equals(item.get("external_evidence"))
          || !"NOT_CERTIFIED".equals(item.get("certification"))
          || !exactFields(transport, "maximum_request_bytes", "maximum_json_part_bytes", "part_number_base")
          || !Long.valueOf(MAX_REQUEST_BYTES).equals(transport.get("maximum_request_bytes"))
          || !Long.valueOf(1024L * 1024L).equals(transport.get("maximum_json_part_bytes"))
          || !Long.valueOf(0).equals(transport.get("part_number_base"))) {
        throw new IOException("SDK_CAPABILITIES_CONTRACT_INVALID");
      }
    }
    if (ordinals.size() != 50 || names.size() != 50) throw new IOException("SDK_CAPABILITIES_CONTRACT_INVALID");
    if (!EXPECTED_CAPABILITY_CATALOG_DIGEST.equals(sha256(canonicalJson(rawSkills)))
        || !EXPECTED_CAPABILITY_DOCUMENT_DIGEST.equals(sha256(canonicalJson(value)))) {
      throw new IOException("SDK_CAPABILITIES_DIGEST_INVALID");
    }
    return value;
  }

  @SuppressWarnings("unchecked")
  private static RemoteError parseRemoteError(HttpResponse<byte[]> response) throws IOException {
    var statusCode = response.statusCode();
    if (statusCode < 400 || statusCode > 599) {
      throw new IOException("SDK_HTTP_STATUS_INVALID");
    }
    var contentTypes = response.headers().allValues("Content-Type");
    if (contentTypes.size() != 1
        || contentTypes.get(0).contains(",")
        || !isJsonMediaType(contentTypes.get(0))) {
      throw new IOException("SDK_ERROR_RESPONSE_CONTENT_TYPE_INVALID");
    }
    var encodings = response.headers().allValues("Content-Encoding");
    if (encodings.size() > 1
        || encodings.size() == 1 && !"identity".equals(encodings.get(0).trim().toLowerCase(Locale.ROOT))) {
      throw new IOException("SDK_ERROR_RESPONSE_CONTENT_ENCODING_INVALID");
    }
    var contentLengths = response.headers().allValues("Content-Length");
    if (contentLengths.size() > 1
        || contentLengths.size() == 1 && !contentLengths.get(0).matches("[0-9]{1,10}")) {
      throw new IOException("SDK_ERROR_RESPONSE_SIZE_INVALID");
    }
    var declared = contentLengths.isEmpty() ? -1L : Long.parseLong(contentLengths.get(0));
    if (declared <= 0 && declared != -1L || declared > MAX_RESPONSE_BYTES) {
      throw new IOException("SDK_ERROR_RESPONSE_TOO_LARGE");
    }
    var bytes = response.body();
    if (bytes.length == 0 || declared >= 0 && bytes.length != declared) {
      throw new IOException("SDK_ERROR_RESPONSE_SIZE_INVALID");
    }
    var rawJson = strictUtf8(bytes, "SDK_ERROR_RESPONSE_INVALID");
    Object parsed;
    try {
      parsed = new StrictJsonParser(rawJson).parse();
    } catch (IOException error) {
      throw new IOException("SDK_ERROR_RESPONSE_INVALID", error);
    }
    if (!(parsed instanceof Map<?, ?> rawMap)) {
      throw new IOException("SDK_ERROR_RESPONSE_CONTRACT_INVALID");
    }
    var value = (Map<String, Object>) rawMap;
    if (!canonicalJson(value).equals(rawJson)) {
      throw new IOException("SDK_ERROR_RESPONSE_CANONICAL_JSON_REQUIRED");
    }
    var fieldsWithTrace = exactFields(value, "schema_version", "status", "code", "retryable", "trace_id");
    var code = value.get("code");
    var retryable = value.get("retryable");
    if (!fieldsWithTrace
        || !"1.0.0".equals(value.get("schema_version"))
        || !(statusCode >= 500 ? "FAILED" : "BLOCKED").equals(value.get("status"))
        || !(code instanceof String publicCode) || !PUBLIC_CODE.matcher(publicCode).matches()
        || !(retryable instanceof Boolean)
        || fieldsWithTrace && !boundedTraceId(value.get("trace_id"))) {
      throw new IOException("SDK_ERROR_RESPONSE_CONTRACT_INVALID");
    }
    return new RemoteError(
        statusCode,
        (String) code,
        (Boolean) retryable,
        (String) value.get("trace_id")
    );
  }

  private static boolean numericLoopbackHost(String value) {
    if (value == null) return false;
    var host = value.toLowerCase(Locale.ROOT);
    if (host.startsWith("[") && host.endsWith("]")) host = host.substring(1, host.length() - 1);
    if ("::1".equals(host)) return true;
    var segments = host.split("\\.", -1);
    if (segments.length != 4 || !"127".equals(segments[0])) return false;
    for (var segment : segments) {
      if (!segment.matches("(?:0|[1-9][0-9]{0,2})") || Integer.parseInt(segment) > 255) return false;
    }
    return true;
  }

  public MultimodalIntakeClient(URI baseUri, String bearerToken) {
    this(baseUri, bearerToken, Duration.ofSeconds(30));
  }

  public MultimodalIntakeClient(URI baseUri, String bearerToken, Duration requestTimeout) {
    this.baseUri = Objects.requireNonNull(baseUri, "baseUri");
    if (!validBearerToken(bearerToken)) throw new IllegalArgumentException("SDK_TOKEN_INVALID");
    if (requestTimeout == null
        || requestTimeout.compareTo(MIN_TIMEOUT) < 0
        || requestTimeout.compareTo(MAX_TIMEOUT) > 0) {
      throw new IllegalArgumentException("SDK_TIMEOUT_INVALID");
    }
    this.bearerToken = bearerToken;
    this.requestTimeout = requestTimeout;
    var host = baseUri.getHost() == null ? null : baseUri.getHost().toLowerCase(Locale.ROOT);
    var loopback = numericLoopbackHost(host);
    var scheme = baseUri.getScheme() == null ? "" : baseUri.getScheme().toLowerCase(Locale.ROOT);
    if (host == null || !("https".equals(scheme) || ("http".equals(scheme) && loopback))
        || baseUri.getUserInfo() != null || baseUri.getQuery() != null || baseUri.getFragment() != null) {
      throw new IllegalArgumentException("SDK_BASE_URL_HTTPS_OR_LOOPBACK_REQUIRED");
    }
    var connectTimeout = requestTimeout.compareTo(Duration.ofSeconds(10)) < 0
        ? requestTimeout
        : Duration.ofSeconds(10);
    this.http = HttpClient.newBuilder().followRedirects(HttpClient.Redirect.NEVER).connectTimeout(connectTimeout).build();
  }

  private static boolean validBearerToken(String token) {
    if (token == null || token.length() < MIN_TOKEN_LENGTH || token.length() > MAX_TOKEN_LENGTH) return false;
    for (var index = 0; index < token.length(); index += 1) {
      var character = token.charAt(index);
      if (character < 0x21 || character > 0x7e) return false;
    }
    return true;
  }

  private static boolean isJsonMediaType(String contentType) {
    var separator = contentType.indexOf(';');
    var mediaType = (separator < 0 ? contentType : contentType.substring(0, separator))
        .trim()
        .toLowerCase(Locale.ROOT);
    return "application/json".equals(mediaType) || JSON_SUFFIX_MEDIA_TYPE.matcher(mediaType).matches();
  }

  private static boolean timestamp(Object value) {
    if (!(value instanceof String item)) return false;
    try {
      OffsetDateTime.parse(item);
      return true;
    } catch (DateTimeParseException error) {
      return false;
    }
  }

  private static boolean exactFields(Map<String, Object> value, String... fields) {
    return value.keySet().equals(Set.of(fields));
  }

  private static long integer(Map<String, Object> value, String field) throws IOException {
    var item = value.get(field);
    if (!(item instanceof Long number) || number < 0 || number > MAX_SAFE_JSON_INTEGER) {
      throw new IOException("SDK_PROGRESS_ENVELOPE_INVALID");
    }
    return number;
  }

  private static Map<String, Object> validateProgressDocument(
      Map<String, Object> value,
      String resourceKind,
      String resourceId,
      String eventName,
      String eventId,
      String requestedCursor
  ) throws IOException {
    var sequence = integer(value, "sequence_number");
    var rawDigest = value.get("content_digest");
    var digestMatcher = rawDigest instanceof String item ? CONTENT_DIGEST.matcher(item) : null;
    if (!"1.0.0".equals(value.get("schema_version"))
        || !resourceId.equals(value.get("resource_id"))
        || digestMatcher == null
        || !digestMatcher.matches()) {
      throw new IOException("SDK_PROGRESS_ENVELOPE_INVALID");
    }
    var parsedRequested = strictCursor(requestedCursor);
    if ("heartbeat".equals(eventName)) {
      if (!exactFields(value, "schema_version", "kind", "resource_id", "sequence_number", "status", "content_digest", "cursor")
          || !(resourceKind.toUpperCase(Locale.ROOT) + "_PROGRESS_HEARTBEAT").equals(value.get("kind"))
          || !"NO_CHANGE".equals(value.get("status"))
          || eventId != null
          || !Objects.equals(value.get("cursor"), requestedCursor)
          || sequence != (parsedRequested == null ? 0 : parsedRequested.sequence())) {
        throw new IOException("SDK_PROGRESS_HEARTBEAT_INVALID");
      }
    } else if ("progress".equals(eventName) && "task".equals(resourceKind)) {
      if (!exactFields(value, "schema_version", "kind", "resource_id", "sequence_number", "event_type", "state", "previous_state", "occurred_at", "content_digest", "cursor")
          || !"TASK_PROGRESS".equals(value.get("kind"))
          || !"durable.task.transitioned".equals(value.get("event_type"))
          || !TASK_STATES.contains(value.get("state"))
          || !TASK_STATES.contains(value.get("previous_state"))
          || !TASK_TRANSITIONS.get(value.get("previous_state")).contains(value.get("state"))
          || !timestamp(value.get("occurred_at"))) {
        throw new IOException("SDK_PROGRESS_ENVELOPE_INVALID");
      }
    } else if ("progress".equals(eventName) && "job".equals(resourceKind)) {
      var attempt = integer(value, "attempt");
      var maximumAttempts = integer(value, "max_attempts");
      if (!exactFields(value, "schema_version", "kind", "resource_id", "sequence_number", "event_type", "state", "result_status", "attempt", "max_attempts", "occurred_at", "content_digest", "cursor")
          || !"JOB_PROGRESS".equals(value.get("kind"))
          || !"processing.job.snapshot".equals(value.get("event_type"))
          || !JOB_RESULT_BY_STATE.containsKey(value.get("state"))
          || !Objects.equals(JOB_RESULT_BY_STATE.get(value.get("state")), value.get("result_status"))
          || maximumAttempts < 1
          || attempt > maximumAttempts
          || !timestamp(value.get("occurred_at"))) {
        throw new IOException("SDK_PROGRESS_ENVELOPE_INVALID");
      }
    } else throw new IOException("SDK_PROGRESS_ENVELOPE_INVALID");
    var unsigned = new LinkedHashMap<>(value);
    unsigned.remove("content_digest");
    unsigned.remove("cursor");
    var expectedDigest = sha256(canonicalJson(unsigned));
    if (!MessageDigest.isEqual(
        digestMatcher.group(1).getBytes(StandardCharsets.US_ASCII),
        expectedDigest.getBytes(StandardCharsets.US_ASCII)
    )) throw new IOException("SDK_PROGRESS_DIGEST_INVALID");
    if ("progress".equals(eventName)) {
      var expectedCursor = "p1-" + sequence + "-" + expectedDigest;
      if (!expectedCursor.equals(value.get("cursor"))
          || !expectedCursor.equals(eventId)
          || parsedRequested != null && sequence <= parsedRequested.sequence()) {
        throw new IOException("SDK_PROGRESS_CURSOR_INVALID");
      }
    }
    return immutableMap(value);
  }

  @SuppressWarnings("unchecked")
  public static ProgressBatch parseProgressSse(
      byte[] payload,
      String resourceKind,
      String rawResourceId,
      String requestedCursor
  ) throws IOException {
    var resourceId = strictResourceId(rawResourceId);
    var parsedRequested = strictCursor(requestedCursor);
    if (!Set.of("task", "job").contains(resourceKind)) {
      throw new IllegalArgumentException("SDK_PROGRESS_RESOURCE_KIND_INVALID");
    }
    if (payload == null || payload.length < 2 || payload.length > MAX_RESPONSE_BYTES) {
      throw new IOException("SDK_PROGRESS_RESPONSE_TOO_LARGE");
    }
    var source = strictUtf8(payload, "SDK_PROGRESS_SSE_INVALID");
    if (source.indexOf('\r') >= 0 || source.indexOf('\0') >= 0 || !source.endsWith("\n\n")) {
      throw new IOException("SDK_PROGRESS_SSE_INVALID");
    }
    var frames = source.substring(0, source.length() - 2).split("\n\n", -1);
    if (frames.length < 1 || frames.length > MAX_PROGRESS_DOCUMENTS) {
      throw new IOException("SDK_PROGRESS_SSE_INVALID");
    }
    var documents = new ArrayList<Map<String, Object>>();
    Map<String, Object> heartbeat = null;
    var previousSequence = parsedRequested == null ? 0 : parsedRequested.sequence();
    String previousTaskState = null;
    for (var frame : frames) {
      var lines = new ArrayList<>(List.of(frame.split("\n", -1)));
      String eventId = null;
      if (lines.size() == 3 && lines.get(0).startsWith("id: ")) {
        eventId = lines.remove(0).substring(4);
      }
      if (lines.size() != 2 || !lines.get(0).startsWith("event: ") || !lines.get(1).startsWith("data: ")) {
        throw new IOException("SDK_PROGRESS_SSE_INVALID");
      }
      var eventName = lines.get(0).substring(7);
      var rawJson = lines.get(1).substring(6);
      var parsed = new StrictJsonParser(rawJson).parse();
      if (!(parsed instanceof Map<?, ?> rawMap)) throw new IOException("SDK_PROGRESS_ENVELOPE_INVALID");
      var value = (Map<String, Object>) rawMap;
      if (!canonicalJson(value).equals(rawJson)) throw new IOException("SDK_PROGRESS_CANONICAL_JSON_REQUIRED");
      var document = validateProgressDocument(
          value, resourceKind, resourceId, eventName, eventId, requestedCursor
      );
      if ("heartbeat".equals(eventName)) {
        if (heartbeat != null || !documents.isEmpty() || frames.length != 1) {
          throw new IOException("SDK_PROGRESS_HEARTBEAT_INVALID");
        }
        heartbeat = document;
        continue;
      }
      if ("job".equals(resourceKind) && !documents.isEmpty()) {
        // The job endpoint returns exactly one snapshot or one heartbeat; it
        // is not a task-like transition history.
        throw new IOException("SDK_PROGRESS_HISTORY_INVALID");
      }
      var sequence = (Long) document.get("sequence_number");
      if (("task".equals(resourceKind) && sequence != previousSequence + 1) || sequence <= previousSequence) {
        throw new IOException("SDK_PROGRESS_SEQUENCE_INVALID");
      }
      previousSequence = sequence;
      if ("task".equals(resourceKind)) {
        var documentPreviousState = (String) document.get("previous_state");
        if (previousTaskState == null && parsedRequested == null
            && !"PENDING".equals(documentPreviousState)) {
          throw new IOException("SDK_PROGRESS_HISTORY_INVALID");
        }
        if (previousTaskState != null && !previousTaskState.equals(documentPreviousState)) {
          throw new IOException("SDK_PROGRESS_HISTORY_INVALID");
        }
        // A p1 cursor binds sequence and digest but cannot reveal prior task state.
        // Only states observed inside this response batch can extend the chain.
        previousTaskState = (String) document.get("state");
      }
      documents.add(document);
    }
    var nextCursor = !documents.isEmpty()
        ? (String) documents.get(documents.size() - 1).get("cursor")
        : heartbeat == null ? null : (String) heartbeat.get("cursor");
    return new ProgressBatch(resourceKind, resourceId, documents, heartbeat, requestedCursor, nextCursor);
  }

  public byte[] capabilities() throws IOException, InterruptedException {
    return send("GET", CAPABILITIES_PATH, null, null);
  }

  public byte[] execute(byte[] strictJsonRequest) throws IOException, InterruptedException {
    Objects.requireNonNull(strictJsonRequest, "strictJsonRequest");
    var expected = parseExecutionRequest(strictJsonRequest);
    return send("POST", EXECUTE_PATH, expected.canonicalBody(), expected);
  }

  /** Registry-typed entry point; the byte-oriented execute method is the low-level transport. */
  public byte[] execute(
      RegisteredOperation registered,
      ExecutionContext context,
      Map<String, Object> input
  ) throws IOException, InterruptedException {
    Objects.requireNonNull(registered, "registered");
    Objects.requireNonNull(context, "context");
    Objects.requireNonNull(input, "input");
    var document = new LinkedHashMap<String, Object>();
    document.put("schema_version", "1.0.0");
    document.put("skill", registered.skill());
    document.put("operation", registered.operation());
    document.put("tenant_id", context.tenantId());
    document.put("project_id", context.projectId());
    document.put("actor_id", context.actorId());
    document.put("idempotency_key", context.idempotencyKey());
    document.put("trace_id", context.traceId());
    document.put("input", new LinkedHashMap<>(input));
    return execute(canonicalJson(document).getBytes(StandardCharsets.UTF_8));
  }

  public byte[] evaluate(
      ExecutionContext context,
      EvaluationSubject subject,
      List<EvaluationEvidence> evidence
  ) throws IOException, InterruptedException {
    Objects.requireNonNull(subject, "subject");
    if (evidence == null || evidence.isEmpty() || evidence.size() > 240) {
      throw new IllegalArgumentException("OPERATION_INPUT_SHAPE_INVALID");
    }
    var items = new ArrayList<Object>();
    for (var item : evidence) items.add(Objects.requireNonNull(item, "evidence").toMap());
    return execute(
        new RegisteredOperation("elmos-multimodal-evaluation-framework", "evaluate"),
        context,
        Map.of("subject", subject.toMap(), "evidence", items)
    );
  }

  public byte[] verifyEvaluation(ExecutionContext context, String runId)
      throws IOException, InterruptedException {
    return execute(
        new RegisteredOperation("elmos-multimodal-evaluation-framework", "verify"),
        context, Map.of("run_id", runId)
    );
  }

  public byte[] getEvaluationRun(ExecutionContext context, String runId)
      throws IOException, InterruptedException {
    return execute(
        new RegisteredOperation("elmos-multimodal-evaluation-framework", "get_run"),
        context, Map.of("run_id", runId)
    );
  }

  public byte[] evaluationCatalog(ExecutionContext context)
      throws IOException, InterruptedException {
    return execute(
        new RegisteredOperation("elmos-multimodal-evaluation-framework", "catalog"),
        context, Map.of()
    );
  }

  public byte[] beginProjectPackage(
      ExecutionContext context, long expectedEntryCount, String sessionId
  ) throws IOException, InterruptedException {
    var input = new LinkedHashMap<String, Object>();
    input.put("expected_entry_count", expectedEntryCount);
    if (sessionId != null) input.put("session_id", sessionId);
    return execute(new RegisteredOperation("elmos-folder-tree-input", "begin"), context, input);
  }

  public byte[] appendProjectPackage(
      ExecutionContext context, String sessionId, long chunkIndex, List<ProjectPackageEntry> entries
  ) throws IOException, InterruptedException {
    if (entries == null || entries.isEmpty() || entries.size() > 1_000) {
      throw new IllegalArgumentException("OPERATION_INPUT_SHAPE_INVALID");
    }
    var items = new ArrayList<Object>();
    for (var entry : entries) items.add(Objects.requireNonNull(entry, "entry").toMap());
    return execute(
        new RegisteredOperation("elmos-folder-tree-input", "append"), context,
        Map.of("session_id", sessionId, "chunk_index", chunkIndex, "entries", items)
    );
  }

  public byte[] confirmProjectPackagePart(
      ExecutionContext context,
      String sessionId,
      String path,
      long partNumber,
      byte[] data
  ) throws IOException, InterruptedException {
    Objects.requireNonNull(data, "data");
    return execute(
        new RegisteredOperation("elmos-resumable-multi-file-folder-upload", "confirm_part"),
        context,
        Map.of(
            "session_id", sessionId,
            "path", path,
            "part_number", partNumber,
            "byte_count", (long) data.length,
            "part_digest", "sha256:" + sha256Bytes(data),
            "data_base64", Base64.getEncoder().encodeToString(data)
        )
    );
  }

  public ProgressBatch taskProgress(ProgressContext context, String taskId, String cursor)
      throws IOException, InterruptedException {
    return progress("task", context, taskId, cursor);
  }

  public ProgressBatch taskProgress(ProgressContext context, String taskId)
      throws IOException, InterruptedException {
    return taskProgress(context, taskId, null);
  }

  public ProgressBatch jobProgress(ProgressContext context, String jobId, String cursor)
      throws IOException, InterruptedException {
    return progress("job", context, jobId, cursor);
  }

  public ProgressBatch jobProgress(ProgressContext context, String jobId)
      throws IOException, InterruptedException {
    return jobProgress(context, jobId, null);
  }

  private ProgressBatch progress(
      String resourceKind,
      ProgressContext context,
      String rawResourceId,
      String cursor
  )
      throws IOException, InterruptedException {
    Objects.requireNonNull(context, "context");
    var resourceId = strictResourceId(rawResourceId);
    strictCursor(cursor);
    var prefix = "task".equals(resourceKind) ? PROGRESS_TASK_EVENTS_PREFIX : PROGRESS_JOB_EVENTS_PREFIX;
    var target = prefix + resourceId + "/events" + (cursor == null ? "" : "?cursor=" + cursor);
    var request = HttpRequest.newBuilder(baseUri.resolve(target)).timeout(requestTimeout)
        .header("Accept", "text/event-stream")
        .header("Authorization", "Bearer " + bearerToken)
        .header("X-ELMOS-Bound-Tenant", context.tenantId())
        .header("X-ELMOS-Bound-Project", context.projectId())
        .header("X-ELMOS-Bound-Actor", context.actorId())
        .GET()
        .build();
    var response = http.send(request, boundedBodyHandler("SDK_PROGRESS_RESPONSE_TOO_LARGE"));
    if (response.statusCode() != 200) {
      throw parseRemoteError(response);
    }
    var contentTypes = response.headers().allValues("Content-Type");
    if (contentTypes.size() != 1
        || !"text/event-stream".equals(contentTypes.get(0).split(";", 2)[0].trim().toLowerCase(Locale.ROOT))) {
      throw new IOException("SDK_PROGRESS_CONTENT_TYPE_INVALID");
    }
    var encodings = response.headers().allValues("Content-Encoding");
    if (encodings.size() > 1
        || encodings.size() == 1 && !"identity".equals(encodings.get(0).trim().toLowerCase(Locale.ROOT))) {
      throw new IOException("SDK_PROGRESS_CONTENT_ENCODING_INVALID");
    }
    var contentLengths = response.headers().allValues("Content-Length");
    if (contentLengths.size() > 1
        || contentLengths.size() == 1 && !contentLengths.get(0).matches("[0-9]{1,10}")) {
      throw new IOException("SDK_PROGRESS_SIZE_INVALID");
    }
    var declared = contentLengths.isEmpty() ? -1L : Long.parseLong(contentLengths.get(0));
    if (declared <= 0 && declared != -1L || declared > MAX_RESPONSE_BYTES) {
      throw new IOException("SDK_PROGRESS_RESPONSE_TOO_LARGE");
    }
    var bytes = response.body();
    if (bytes.length == 0 || declared >= 0 && bytes.length != declared) {
      throw new IOException("SDK_PROGRESS_SIZE_INVALID");
    }
    return parseProgressSse(bytes, resourceKind, resourceId, cursor);
  }

  private byte[] send(
      String method,
      String path,
      byte[] body,
      ExpectedExecutionRequest expectedRequest
  ) throws IOException, InterruptedException {
    var builder = HttpRequest.newBuilder(baseUri.resolve(path)).timeout(requestTimeout)
        .header("Accept", "application/json").header("Authorization", "Bearer " + bearerToken);
    if (body == null) builder.method(method, HttpRequest.BodyPublishers.noBody());
    else builder.header("Content-Type", "application/json").method(method, HttpRequest.BodyPublishers.ofByteArray(body));
    var response = http.send(builder.build(), boundedBodyHandler("SDK_RESPONSE_TOO_LARGE"));
    if (response.statusCode() != 200) throw parseRemoteError(response);
    var contentTypes = response.headers().allValues("Content-Type");
    if (contentTypes.size() != 1 || !isJsonMediaType(contentTypes.get(0))) {
      throw new IOException("SDK_RESPONSE_CONTENT_TYPE_INVALID");
    }
    var encodings = response.headers().allValues("Content-Encoding");
    if (encodings.size() > 1
        || encodings.size() == 1 && !"identity".equals(encodings.get(0).trim().toLowerCase(Locale.ROOT))) {
      throw new IOException("SDK_RESPONSE_CONTENT_ENCODING_INVALID");
    }
    var contentLengths = response.headers().allValues("Content-Length");
    if (contentLengths.size() > 1 || contentLengths.size() == 1 && !contentLengths.get(0).matches("[0-9]{1,10}")) {
      throw new IOException("SDK_RESPONSE_SIZE_INVALID");
    }
    var declared = contentLengths.isEmpty() ? -1L : Long.parseLong(contentLengths.get(0));
    if (declared <= 0 && declared != -1L || declared > MAX_RESPONSE_BYTES) {
      throw new IOException("SDK_RESPONSE_TOO_LARGE");
    }
    var bytes = response.body();
    if (bytes.length == 0 || declared >= 0 && bytes.length != declared) {
      throw new IOException("SDK_RESPONSE_SIZE_INVALID");
    }
    var rawJson = strictUtf8(bytes, "SDK_RESPONSE_INVALID");
    var value = parseStrictObject(bytes, "SDK_RESPONSE_INVALID");
    if (!canonicalJson(value).equals(rawJson)) {
      throw new IOException("SDK_RESPONSE_CANONICAL_JSON_REQUIRED");
    }
    if ("GET".equals(method) && CAPABILITIES_PATH.equals(path)
        && body == null && expectedRequest == null) {
      validateCapabilityResponse(value);
    } else if ("POST".equals(method) && EXECUTE_PATH.equals(path)
        && body != null && expectedRequest != null) {
      validateExecutionResult(value, expectedRequest);
    } else {
      throw new IOException("SDK_RESPONSE_ROUTE_INVALID");
    }
    // Preserve the byte[] API while returning only a reserialized, validated document.
    return canonicalJson(value).getBytes(StandardCharsets.UTF_8);
  }
}
