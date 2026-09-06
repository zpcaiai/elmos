package io.elmos.controlplane;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.persistence.JdbcObjectStorageStore;
import io.elmos.proofloop.ProofLoopModels;
import io.elmos.workflow.ExecutionJobPort;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;

/** Tenant-facing durable execution API. Tenant and actor always come from auth. */
@RestController
@RequestMapping("/api/v1/execution/jobs")
public class ExecutionJobController {
    private static final int MAX_LIST_OFFSET = 10_000;

    private final ExecutionJobPort jobs;
    private final JdbcObjectStorageStore artifacts;
    private final ObjectMapper json;
    private final Map<ExecutionJobPort.BusinessLine, RuntimeProfile> profiles;
    private TranslationExecutionPreparation translations;

    @org.springframework.beans.factory.annotation.Autowired
    void translationPreparation(TranslationExecutionPreparation preparation) { this.translations = preparation; }

    record RuntimeProfile(String permission, String capability, String image) {}

    public ExecutionJobController(
            ExecutionJobPort jobs,
            JdbcObjectStorageStore artifacts,
            ObjectMapper json,
            @Value("${elmos.execution.images.generation:}") String generationImage,
            @Value("${elmos.execution.images.translation:}") String translationImage,
            @Value("${elmos.execution.images.spring-upgrade:}") String springImage,
            @Value("${elmos.execution.images.repository-workspace:}") String repositoryImage,
            @Value("${elmos.execution.images.modernization-proof:}") String modernizationProofImage
    ) {
        this.jobs = jobs;
        this.artifacts = artifacts;
        this.json = json;
        this.profiles = Map.of(
                ExecutionJobPort.BusinessLine.GENERATION,
                new RuntimeProfile("generation:execute", "generation:multi", generationImage),
                ExecutionJobPort.BusinessLine.TRANSLATION,
                new RuntimeProfile("translation:execute", "translation:multi", translationImage),
                ExecutionJobPort.BusinessLine.SPRING_UPGRADE,
                new RuntimeProfile("spring:execute", "spring:upgrade", springImage),
                ExecutionJobPort.BusinessLine.REPOSITORY_WORKSPACE,
                new RuntimeProfile("repository:write", "repository:workspace", repositoryImage),
                ExecutionJobPort.BusinessLine.MODERNIZATION_PROOF,
                new RuntimeProfile("modernization:execute", "modernization:proof-loop", modernizationProofImage));
    }

    public record EnqueueRequest(
            String businessLine,
            String jobKind,
            String idempotencyKey,
            Map<String, Object> payload,
            Short priority,
            Integer budgetWallSeconds,
            Short maxAttempts
    ) {}

    @PostMapping
    public ResponseEntity<?> enqueue(@RequestBody EnqueueRequest request) {
        ExecutionJobPort.BusinessLine line = parseLine(request.businessLine());
        ControlPlanePrincipal principal = principal(line);
        RuntimeProfile profile = profiles.get(line);
        if (!profile.image().matches("^[a-z0-9][a-z0-9._/-]*(:[0-9]+)?/?[a-z0-9._/-]*@sha256:[0-9a-f]{64}$")) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body(Map.of(
                    "status", "CONFIGURATION_REQUIRED",
                    "code", "ELMOS_RUNNER_IMAGE_NOT_CONFIGURED"));
        }
        Map<String, Object> payload = request.payload() == null ? Map.of() : request.payload();
        rejectSensitivePayload(payload);
        String idempotencyKey = require(request.idempotencyKey(), 160, "ELMOS_IDEMPOTENCY_KEY_INVALID");
        String jobKind = line == ExecutionJobPort.BusinessLine.MODERNIZATION_PROOF
                ? "batch105-108-proof-loop"
                : require(request.jobKind(), 64, "ELMOS_JOB_KIND_INVALID");
        String jobId = "job-" + UUID.randomUUID();
        if (line == ExecutionJobPort.BusinessLine.TRANSLATION) {
            if (translations == null) {
                return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body(Map.of(
                        "status", "CONFIGURATION_REQUIRED", "code", "TRANSLATION_HOSTED_PREPARATION_REQUIRED"));
            }
            if (!TranslationExecutionPreparation.KIND.equals(jobKind)) {
                throw new ExecutionJobPort.ExecutionStateException("TRANSLATION_JOB_KIND_INVALID");
            }
            var replay=jobs.findByIdempotencyKey(principal.organizationId(),idempotencyKey);
            if (replay.isPresent()) {
                var existing=jobs.find(principal.organizationId(),replay.get().jobId()).orElseThrow();
                var previous=jobs.requestPayload(principal.organizationId(),existing.jobId()).orElseThrow();
                if (existing.businessLine()!=line || !existing.jobKind().equals(jobKind)
                        || !existing.actorId().equals(principal.actorId())
                        || !payload.keySet().equals(java.util.Set.of("repositoryWorkspaceId","casesBundleId","sourceLanguage","targetLanguage")))
                    throw new ExecutionJobPort.ExecutionStateException("ELMOS_EXECUTION_IDEMPOTENCY_CONFLICT");
                for (var field:payload.entrySet()) if (!java.util.Objects.equals(previous.get(field.getKey()),field.getValue()))
                    throw new ExecutionJobPort.ExecutionStateException("ELMOS_EXECUTION_IDEMPOTENCY_CONFLICT");
                return ResponseEntity.accepted().body(Map.of("jobId",existing.jobId(),"status",existing.status(),
                        "requestDigest",replay.get().requestDigest()));
            }
            payload = translations.prepare(principal, payload, idempotencyKey);
        }
        if (line == ExecutionJobPort.BusinessLine.MODERNIZATION_PROOF) {
            payload = modernizationProofPayload(payload, principal, jobId);
        }
        String digest = digest(payload);
        ExecutionJobPort.EnqueueCommand command = new ExecutionJobPort.EnqueueCommand(
                jobId,
                principal.organizationId(),
                principal.actorId(),
                line,
                jobKind,
                idempotencyKey,
                digest,
                payload,
                profile.capability(),
                profile.image(),
                request.priority() == null ? (short) 100 : request.priority(),
                request.budgetWallSeconds() == null ? 3600 : request.budgetWallSeconds(),
                line == ExecutionJobPort.BusinessLine.TRANSLATION ? (short) 1
                        : request.maxAttempts() == null ? (short) 1 : request.maxAttempts());
        String persisted = line == ExecutionJobPort.BusinessLine.TRANSLATION
                ? translations.enqueue(jobs, command) : jobs.enqueue(command);
        return ResponseEntity.accepted().body(Map.of(
                "jobId", persisted,
                "status", "QUEUED",
                "requestDigest", digest));
    }

    @GetMapping("/{jobId}")
    public ResponseEntity<?> find(@PathVariable String jobId) {
        ControlPlanePrincipal principal = current();
        return jobs.find(principal.organizationId(), jobId)
                .<ResponseEntity<?>>map(job -> {
                    principal.require(
                            principal.organizationId(),
                            principal.actorId(),
                            profiles.get(job.businessLine()).permission());
                    return ResponseEntity.ok(jobResponse(job));
                })
                .orElseGet(() -> ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of(
                        "status", "ERROR", "code", "ELMOS_EXECUTION_JOB_UNKNOWN")));
    }

    @GetMapping("/translation-readiness")
    public ResponseEntity<?> translationReadiness() {
        principal(ExecutionJobPort.BusinessLine.TRANSLATION);
        String image=profiles.get(ExecutionJobPort.BusinessLine.TRANSLATION).image();
        if (translations == null || !image.matches("^[a-z0-9][a-z0-9._/-]*(:[0-9]+)?/?[a-z0-9._/-]*@sha256:[0-9a-f]{64}$"))
            return ResponseEntity.status(503).body(Map.of("status","BLOCKED","code","TRANSLATION_HOSTED_CONFIGURATION_REQUIRED"));
        translations.requireSubmissionConfiguration();
        return ResponseEntity.ok(Map.of("status","READY","isolation","ROOTLESS_CONTAINER","sourceStorage","READ_ONLY",
                "reason","QUEUE_ADMISSION_CONFIGURED_RUNTIME_EVIDENCE_NOT_RUN","executionStatus","NOT_RUN"));
    }

    private Map<String, Object> jobResponse(ExecutionJobPort.JobView job) {
        Map<String, Object> response = new java.util.LinkedHashMap<>(
                json.convertValue(job, new com.fasterxml.jackson.core.type.TypeReference<>() {}));
        response.put("artifacts", artifacts.artifactsFor(job.organizationId(), job.jobId()));
        if (job.businessLine() == ExecutionJobPort.BusinessLine.TRANSLATION
                && TranslationExecutionPreparation.KIND.equals(job.jobKind())) {
            Map<String, Object> payload = jobs.requestPayload(job.organizationId(), job.jobId())
                    .orElseThrow(() -> new ExecutionJobPort.ExecutionStateException("TRANSLATION_INPUT_MISSING"));
            Map<String, Object> summary = new java.util.LinkedHashMap<>(payload);
            summary.remove("input"); // Object identity is a runner capability, not browser routing authority.
            Object input = payload.get("input");
            if (input instanceof Map<?, ?> object) summary.put("inputSha256", object.get("sha256"));
            response.put("translation", summary);
        }
        return response;
    }

    @GetMapping
    public List<ExecutionJobPort.JobView> list(
            @RequestParam(required = false) String businessLine,
            @RequestParam(defaultValue = "50") int limit,
            @RequestParam(defaultValue = "0") int offset
    ) {
        ControlPlanePrincipal principal = current();
        ExecutionJobPort.BusinessLine line = businessLine == null || businessLine.isBlank()
                ? null : parseLine(businessLine);
        if (line == null) {
            principal.require(
                    principal.organizationId(), principal.actorId(), "admin:read");
        } else {
            RuntimeProfile profile = profiles.get(line);
            principal.require(principal.organizationId(), principal.actorId(), profile.permission());
        }
        return jobs.list(
                principal.organizationId(), line,
                requireListLimit(limit), requireListOffset(offset));
    }

    @DeleteMapping("/{jobId}")
    public ResponseEntity<?> cancel(@PathVariable String jobId) {
        ControlPlanePrincipal principal = current();
        ExecutionJobPort.JobView job = jobs.find(principal.organizationId(), jobId)
                .orElseThrow(() -> new ExecutionJobPort.ExecutionStateException(
                        "ELMOS_EXECUTION_JOB_UNKNOWN"));
        principal.require(
                principal.organizationId(),
                principal.actorId(),
                profiles.get(job.businessLine()).permission());
        return ResponseEntity.accepted().body(Map.of(
                "jobId", jobId,
                "status", jobs.requestCancel(
                        principal.organizationId(), jobId, principal.actorId()).name()));
    }

    private ControlPlanePrincipal principal(ExecutionJobPort.BusinessLine line) {
        ControlPlanePrincipal principal = current();
        principal.require(
                principal.organizationId(),
                principal.actorId(),
                profiles.get(line).permission());
        return principal;
    }

    private static ControlPlanePrincipal current() {
        return ControlPlanePrincipal.current()
                .orElseThrow(() -> new AccessDeniedException("CONTROL_PLANE_AUTH_REQUIRED"));
    }

    private ExecutionJobPort.BusinessLine parseLine(String value) {
        try {
            return ExecutionJobPort.BusinessLine.valueOf(
                    value == null ? "" : value.trim().toUpperCase(Locale.ROOT));
        } catch (IllegalArgumentException ex) {
            throw new ExecutionJobPort.ExecutionStateException(
                    "ELMOS_EXECUTION_BUSINESS_LINE_INVALID");
        }
    }

    private String digest(Map<String, Object> payload) {
        try {
            byte[] canonical = json.writer()
                    .with(com.fasterxml.jackson.databind.SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS)
                    .writeValueAsBytes(payload);
            return HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256").digest(canonical));
        } catch (Exception ex) {
            throw new ExecutionJobPort.ExecutionStateException(
                    "ELMOS_EXECUTION_PAYLOAD_UNSERIALIZABLE");
        }
    }

    private Map<String, Object> modernizationProofPayload(
            Map<String, Object> payload,
            ControlPlanePrincipal principal,
            String jobId
    ) {
        try {
            String targetSkillId = requiredPayloadString(payload, "targetSkillId", 8,
                    "ELMOS_PROOF_TARGET_SKILL_INVALID");
            ProofLoopModels.Subject subject = new ProofLoopModels.Subject(
                    principal.organizationId(),
                    requiredPayloadString(payload, "projectId", 160, "ELMOS_PROOF_PROJECT_INVALID"),
                    requiredPayloadString(payload, "repositoryId", 160, "ELMOS_PROOF_REPOSITORY_INVALID"),
                    stringOrNull(payload.get("baselineCommit")),
                    stringOrNull(payload.get("candidateCommit")),
                    stringOrNull(payload.get("imageDigest")),
                    requiredPayloadString(payload, "policyDigest", 80, "ELMOS_PROOF_POLICY_DIGEST_INVALID"));
            Map<String, Object> inputs = map(payload.get("inputs"));
            Map<String, ProofLoopModels.EvidenceAssertion> evidence = evidence(payload.get("evidence"));
            ProofLoopModels.ExecutionRequest execution = new ProofLoopModels.ExecutionRequest(
                    jobId, jobId + ":" + targetSkillId, targetSkillId, principal.actorId(), subject,
                    java.time.Instant.now(), inputs, evidence);
            return Map.of(
                    "schemaVersion", 1,
                    "targetSkillId", targetSkillId,
                    "execution", json.convertValue(execution,
                            new com.fasterxml.jackson.core.type.TypeReference<Map<String, Object>>() {}));
        } catch (ExecutionJobPort.ExecutionStateException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            throw new ExecutionJobPort.ExecutionStateException("ELMOS_PROOF_REQUEST_INVALID");
        }
    }

    private Map<String, ProofLoopModels.EvidenceAssertion> evidence(Object raw) {
        if (raw == null) return Map.of();
        return json.convertValue(raw, new com.fasterxml.jackson.core.type.TypeReference<>() {});
    }

    private static Map<String, Object> map(Object raw) {
        if (raw == null) return Map.of();
        if (!(raw instanceof Map<?, ?> values)) {
            throw new ExecutionJobPort.ExecutionStateException("ELMOS_PROOF_INPUTS_INVALID");
        }
        Map<String, Object> result = new java.util.LinkedHashMap<>();
        values.forEach((key, value) -> result.put(String.valueOf(key), value));
        return Map.copyOf(result);
    }

    private static String stringOrNull(Object value) {
        return value == null || String.valueOf(value).isBlank() ? null : String.valueOf(value);
    }

    private static String requiredPayloadString(Map<String, Object> payload, String key, int max, String code) {
        Object value = payload.get(key);
        if (!(value instanceof String stringValue)) {
            throw new ExecutionJobPort.ExecutionStateException(code);
        }
        return require(stringValue, max, code);
    }

    private static void rejectSensitivePayload(Object value) {
        if (value instanceof Map<?, ?> map) {
            for (Map.Entry<?, ?> entry : map.entrySet()) {
                String key = String.valueOf(entry.getKey()).toLowerCase(Locale.ROOT);
                if (key.matches(".*(authorization|password|secret|token|credential|api.?key).*")) {
                    throw new ExecutionJobPort.ExecutionStateException(
                            "ELMOS_EXECUTION_SECRET_IN_PAYLOAD");
                }
                rejectSensitivePayload(entry.getValue());
            }
        } else if (value instanceof Iterable<?> iterable) {
            iterable.forEach(ExecutionJobController::rejectSensitivePayload);
        }
    }

    private static String require(String value, int max, String code) {
        String candidate = value == null ? "" : value.trim();
        if (candidate.isEmpty() || candidate.length() > max
                || candidate.getBytes(StandardCharsets.UTF_8).length > max * 4) {
            throw new ExecutionJobPort.ExecutionStateException(code);
        }
        return candidate;
    }

    private static int requireListOffset(int offset) {
        if (offset < 0 || offset > MAX_LIST_OFFSET) {
            throw new ExecutionJobPort.ExecutionStateException("ELMOS_EXECUTION_OFFSET_INVALID");
        }
        return offset;
    }

    private static int requireListLimit(int limit) {
        if (limit < 1 || limit > 100) {
            throw new ExecutionJobPort.ExecutionStateException("ELMOS_EXECUTION_LIMIT_INVALID");
        }
        return limit;
    }

    @ExceptionHandler(ExecutionJobPort.ExecutionStateException.class)
    ResponseEntity<?> executionError(ExecutionJobPort.ExecutionStateException ex) {
        HttpStatus status = switch (ex.code()) {
            case "ELMOS_EXECUTION_JOB_UNKNOWN" -> HttpStatus.NOT_FOUND;
            case "ELMOS_EXECUTION_IDEMPOTENCY_CONFLICT",
                 "ELMOS_EXECUTION_STORAGE_CONFLICT" -> HttpStatus.CONFLICT;
            case "ELMOS_EXECUTION_NO_ACTIVE_ENTITLEMENT",
                 "ELMOS_EXECUTION_QUEUE_DEPTH_EXCEEDED", "TRANSLATION_INPUT_CAPACITY_EXCEEDED",
                 "TRANSLATION_INPUT_TENANT_CAPACITY_EXCEEDED" -> HttpStatus.TOO_MANY_REQUESTS;
            case "TRANSLATION_HOSTED_BILLING_CONTRACT_REQUIRED", "TRANSLATION_REPOSITORY_SERVICE_REQUIRED",
                 "TRANSLATION_INPUT_PREPARATION_FAILED", "TRANSLATION_INPUT_UPLOAD_UNCONFIRMED",
                 "TRANSLATION_HOSTED_CONFIGURATION_REQUIRED", "TRANSLATION_ADMISSION_RUNTIME_REQUIRED",
                 "TRANSLATION_RUNTIME_DATABASE_AUTHORITY_REQUIRED" -> HttpStatus.SERVICE_UNAVAILABLE;
            default -> HttpStatus.BAD_REQUEST;
        };
        return ResponseEntity.status(status).body(Map.of("status", "ERROR", "code", ex.code()));
    }
}
