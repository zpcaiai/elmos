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
import org.springframework.web.bind.annotation.RequestHeader;
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
    private final ExecutionJobPort jobs;
    private final JdbcObjectStorageStore artifacts;
    private final ObjectMapper json;
    private final Map<ExecutionJobPort.BusinessLine, RuntimeProfile> profiles;

    record RuntimeProfile(
            String permission,
            String capability,
            String image,
            String workloadClass,
            int resourceUnits
    ) {}

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
                new RuntimeProfile(
                        "generation:execute", "generation:multi", generationImage,
                        "GENERATION", 2),
                ExecutionJobPort.BusinessLine.TRANSLATION,
                new RuntimeProfile(
                        "translation:execute", "translation:multi", translationImage,
                        "CONVERSION", 3),
                ExecutionJobPort.BusinessLine.SPRING_UPGRADE,
                new RuntimeProfile(
                        "spring:execute", "spring:upgrade", springImage,
                        "CONVERSION", 3),
                ExecutionJobPort.BusinessLine.REPOSITORY_WORKSPACE,
                new RuntimeProfile(
                        "repository:write", "repository:workspace", repositoryImage,
                        "PARSING", 1),
                ExecutionJobPort.BusinessLine.MODERNIZATION_PROOF,
                new RuntimeProfile(
                        "modernization:execute", "modernization:proof-loop", modernizationProofImage,
                        "VALIDATION", 2));
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
    public ResponseEntity<?> enqueue(
            @RequestBody EnqueueRequest request,
            @RequestHeader(value = "X-Request-ID", required = false) String requestId
    ) {
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
        if (line == ExecutionJobPort.BusinessLine.MODERNIZATION_PROOF) {
            payload = modernizationProofPayload(payload, principal, jobId);
        }
        String digest = digest(payload);
        String persisted = jobs.enqueue(new ExecutionJobPort.EnqueueCommand(
                jobId,
                principal.organizationId(),
                principal.accountId(),
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
                request.maxAttempts() == null ? (short) 1 : request.maxAttempts(),
                serverRequestId(requestId),
                profile.workloadClass(),
                profile.resourceUnits()));
        return ResponseEntity.accepted().body(Map.of(
                "jobId", persisted,
                "status", "QUEUED",
                "requestDigest", digest));
    }

    @GetMapping("/{jobId}")
    public ResponseEntity<?> find(@PathVariable String jobId) {
        ControlPlanePrincipal principal = current();
        return jobs.find(context(principal), jobId)
                .<ResponseEntity<?>>map(job -> ResponseEntity.ok(jobResponse(job)))
                .orElseGet(() -> ResponseEntity.status(HttpStatus.NOT_FOUND).body(Map.of(
                        "status", "ERROR", "code", "ELMOS_EXECUTION_JOB_UNKNOWN")));
    }

    private Map<String, Object> jobResponse(ExecutionJobPort.JobView job) {
        Map<String, Object> response = new java.util.LinkedHashMap<>(
                json.convertValue(job, new com.fasterxml.jackson.core.type.TypeReference<>() {}));
        response.put("artifacts", artifacts.artifactsFor(job.organizationId(), job.jobId()));
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
        if (line != null) {
            RuntimeProfile profile = profiles.get(line);
            principal.require(principal.organizationId(), principal.actorId(), profile.permission());
        }
        return jobs.list(context(principal), line, limit, offset);
    }

    @DeleteMapping("/{jobId}")
    public ResponseEntity<?> cancel(@PathVariable String jobId) {
        ControlPlanePrincipal principal = current();
        ExecutionJobPort.AuthenticatedContext context = context(principal);
        ExecutionJobPort.JobView job = jobs.find(context, jobId)
                .orElseThrow(() -> new ExecutionJobPort.ExecutionStateException(
                        "ELMOS_EXECUTION_JOB_UNKNOWN"));
        principal.require(
                principal.organizationId(),
                principal.actorId(),
                profiles.get(job.businessLine()).permission());
        return ResponseEntity.accepted().body(Map.of(
                "jobId", jobId,
                "status", jobs.requestCancel(context, jobId).name()));
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

    private static ExecutionJobPort.AuthenticatedContext context(
            ControlPlanePrincipal principal
    ) {
        return new ExecutionJobPort.AuthenticatedContext(
                principal.organizationId(),
                principal.accountId(),
                principal.actorId(),
                "execution-api-" + UUID.randomUUID());
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

    private static String serverRequestId(String value) {
        if (value != null && value.matches("[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")) {
            return value;
        }
        return UUID.randomUUID().toString();
    }

    @ExceptionHandler(ExecutionJobPort.ExecutionStateException.class)
    ResponseEntity<?> executionError(ExecutionJobPort.ExecutionStateException ex) {
        HttpStatus status = switch (ex.code()) {
            case "ELMOS_EXECUTION_JOB_UNKNOWN" -> HttpStatus.NOT_FOUND;
            case "ELMOS_EXECUTION_IDEMPOTENCY_CONFLICT" -> HttpStatus.CONFLICT;
            case "ELMOS_EXECUTION_NO_ACTIVE_ENTITLEMENT",
                 "ELMOS_EXECUTION_QUEUE_DEPTH_EXCEEDED" -> HttpStatus.TOO_MANY_REQUESTS;
            default -> HttpStatus.BAD_REQUEST;
        };
        return ResponseEntity.status(status).body(Map.of("status", "ERROR", "code", ex.code()));
    }
}
