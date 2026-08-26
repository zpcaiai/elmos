package io.elmos.controlplane;

import io.elmos.workflow.ExecutionJobPort;
import io.elmos.workflow.ExecutionJobPort.CompletionCommand;
import io.elmos.workflow.ExecutionJobPort.HeartbeatCommand;
import io.elmos.workflow.ExecutionJobPort.HeartbeatResult;
import io.elmos.workflow.ExecutionJobPort.LeaseGrant;
import io.elmos.workflow.RunnerRegistrationPort;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.web.bind.annotation.*;

import java.time.Instant;
import java.util.List;
import java.util.Map;

/**
 * Runner-facing control API.
 *
 * <p>This is the only surface a Runner Agent may call. It is intentionally
 * separate from the tenant API: a runner authenticates with its enrolment
 * credential and its per-job lease token, never with a tenant session, and it can
 * never enumerate jobs it was not leased.</p>
 *
 * <p>The control plane still does not execute anything. It hands out leases and
 * records what the runner reports; container lifecycle stays entirely on the
 * runner side.</p>
 */
@RestController
@RequestMapping("/runner/v1")
public class RunnerFleetController {

    private final ExecutionJobPort jobs;
    private final RunnerRegistrationPort fleet;

    public RunnerFleetController(ExecutionJobPort jobs, RunnerRegistrationPort fleet) {
        this.jobs = jobs;
        this.fleet = fleet;
    }

    public record RegisterRequest(
            String runnerNodeId,
            String poolId,
            String agentVersion,
            List<String> capabilities,
            int maxConcurrency,
            String nodeTokenSha256,
            Attestation attestation) {}

    public record RotateNodeCredentialRequest(
            String runnerNodeId, String nextTokenSha256, String rotationRequestId) {}

    /**
     * Self-declared sandbox facts. They are recorded but they do not by themselves
     * make a node READY: an operator or an automated verifier must confirm them,
     * which is what {@code runner_nodes_ready_requires_attestation} enforces.
     */
    public record Attestation(
            boolean rootless,
            boolean readOnlyRoot,
            boolean capabilitiesDropped,
            boolean networkDefaultDeny,
            String imageAllowlistVersion) {}

    public record ClaimRequest(
            String runnerNodeId,
            List<String> capabilities,
            List<String> availableImages,
            int limit,
            int leaseSeconds) {}

    public record HeartbeatRequest(
            String runnerNodeId, String stage, Short progress,
            Map<String, Object> checkpoint, int leaseSeconds) {}

    public record CompleteRequest(
            String runnerNodeId, String status, String resultStatus, String failureCode) {}

    @PostMapping("/nodes")
    public ResponseEntity<?> register(@RequestBody RegisterRequest request,
                                      @RequestHeader("X-Elmos-Runner-Enrolment") String enrolmentToken) {
        RunnerRegistrationPort.NodeCredential credential =
                fleet.register(request.runnerNodeId(), request.poolId(), request.agentVersion(),
                request.capabilities(), request.maxConcurrency(), enrolmentToken,
                request.nodeTokenSha256(),
                request.attestation().rootless(), request.attestation().readOnlyRoot(),
                request.attestation().capabilitiesDropped(), request.attestation().networkDefaultDeny(),
                request.attestation().imageAllowlistVersion());
        return ResponseEntity.accepted().body(Map.of(
                "status", "REGISTERED",
                "nodeCredentialExpiresAt", credential.expiresAt().toString(),
                "note", "A node stays REGISTERED until its attestation is independently verified."));
    }

    @PostMapping("/nodes/{runnerNodeId}/resume")
    public ResponseEntity<?> resume(
            @PathVariable String runnerNodeId,
            @RequestHeader("X-Elmos-Runner-Token") String nodeToken) {
        RunnerRegistrationPort.NodeCredential credential =
                fleet.resume(runnerNodeId, nodeToken);
        return ResponseEntity.ok(Map.of(
                "status", "RESUMED",
                "nodeCredentialExpiresAt",
                credential.expiresAt().toString()));
    }

    @PostMapping("/nodes/{runnerNodeId}/credential/rotate")
    public ResponseEntity<?> rotateNodeCredential(
            @PathVariable String runnerNodeId,
            @RequestBody RotateNodeCredentialRequest request,
            @RequestHeader("X-Elmos-Runner-Token") String nodeToken) {
        if (!runnerNodeId.equals(request.runnerNodeId())) {
            throw new RunnerRegistrationPort.RunnerAuthenticationException(
                    "ELMOS_RUNNER_NODE_MISMATCH");
        }
        Instant expiresAt = fleet.rotateNodeCredential(
                runnerNodeId, nodeToken,
                request.nextTokenSha256(), request.rotationRequestId());
        return ResponseEntity.ok(Map.of(
                "status", "ROTATED",
                "nodeCredentialExpiresAt", expiresAt.toString()));
    }

    @PostMapping("/nodes/{runnerNodeId}/heartbeat")
    public ResponseEntity<?> nodeHeartbeat(@PathVariable String runnerNodeId,
                                           @RequestHeader("X-Elmos-Runner-Token") String nodeToken) {
        boolean drain = fleet.heartbeat(runnerNodeId, nodeToken);
        return ResponseEntity.ok(Map.of("drainRequested", drain));
    }

    /**
     * Long-poll friendly claim. An empty list is a normal answer and means "nothing
     * for your capabilities right now" - the agent backs off and retries.
     */
    @PostMapping("/leases/claim")
    public ResponseEntity<?> claim(@RequestBody ClaimRequest request,
                                   @RequestHeader("X-Elmos-Runner-Token") String nodeToken) {
        fleet.authorizeNode(request.runnerNodeId(), nodeToken);
        List<LeaseGrant> grants = jobs.claim(
                request.runnerNodeId(), request.capabilities(), request.availableImages(),
                request.limit(), request.leaseSeconds());
        return ResponseEntity.ok(Map.of("leases", grants.stream().map(RunnerFleetController::toWire).toList()));
    }

    @PostMapping("/leases/{leaseId}/heartbeat")
    public ResponseEntity<?> heartbeat(@PathVariable String leaseId,
                                       @RequestBody HeartbeatRequest request,
                                       @RequestHeader("X-Elmos-Lease-Token") String leaseToken) {
        HeartbeatResult result = jobs.heartbeat(new HeartbeatCommand(
                leaseId, request.runnerNodeId(), leaseToken, request.stage(),
                request.progress(), request.checkpoint(),
                clamp(request.leaseSeconds(), 30, 600)));
        // cancelRequested is how a user-initiated cancel reaches the container. The
        // agent is expected to SIGTERM its workload and report CANCELLED.
        return ResponseEntity.ok(Map.of(
                "cancelRequested", result.cancelRequested(),
                "leaseExpiresAt", result.leaseExpiresAt().toString()));
    }

    @PostMapping("/leases/{leaseId}/complete")
    public ResponseEntity<?> complete(@PathVariable String leaseId,
                                      @RequestBody CompleteRequest request,
                                      @RequestHeader("X-Elmos-Lease-Token") String leaseToken) {
        boolean applied = jobs.complete(new CompletionCommand(
                leaseId, request.runnerNodeId(), leaseToken,
                ExecutionJobPort.Status.valueOf(request.status()),
                request.resultStatus() == null ? null : ExecutionJobPort.ResultStatus.valueOf(request.resultStatus()),
                request.failureCode()));
        // applied == false means the job already reached a terminal state. That is a
        // successful, idempotent outcome for a retrying agent, not an error.
        return ResponseEntity.ok(Map.of("applied", applied));
    }

    private static Map<String, Object> toWire(LeaseGrant grant) {
        return Map.ofEntries(
                Map.entry("jobId", grant.jobId()),
                Map.entry("leaseId", grant.leaseId()),
                Map.entry("leaseToken", grant.leaseToken()),
                Map.entry("leaseExpiresAt", grant.leaseExpiresAt().toString()),
                Map.entry("businessLine", grant.businessLine().name()),
                Map.entry("jobKind", grant.jobKind()),
                Map.entry("runnerImage", grant.runnerImage() == null ? "" : grant.runnerImage()),
                Map.entry("budgetWallSeconds", grant.budgetWallSeconds()),
                Map.entry("budgetCpuMillis", grant.budgetCpuMillis()),
                Map.entry("budgetMemoryMib", grant.budgetMemoryMib()),
                Map.entry("attempt", grant.attempt()),
                Map.entry("checkpointCursor", grant.checkpointCursor()),
                Map.entry("requestPayload", grant.requestPayload()));
    }

    private static int clamp(int value, int min, int max) {
        return Math.min(Math.max(value, min), max);
    }

    @ExceptionHandler(ExecutionJobPort.ExecutionStateException.class)
    public ResponseEntity<?> onExecutionState(ExecutionJobPort.ExecutionStateException ex) {
        HttpStatus status = switch (ex.code()) {
            case "ELMOS_RUNNER_UNKNOWN", "ELMOS_LEASE_UNKNOWN" -> HttpStatus.NOT_FOUND;
            case "ELMOS_LEASE_CREDENTIAL_MISMATCH" -> HttpStatus.FORBIDDEN;
            case "ELMOS_LEASE_EXPIRED", "ELMOS_LEASE_NOT_ACTIVE" -> HttpStatus.CONFLICT;
            case "ELMOS_RUNNER_NOT_READY", "ELMOS_RUNNER_ATTESTATION_INCOMPLETE",
                 "ELMOS_RUNNER_HEARTBEAT_STALE" -> HttpStatus.PRECONDITION_FAILED;
            default -> HttpStatus.BAD_REQUEST;
        };
        // Stable code only; the PostgreSQL message never reaches the wire.
        return ResponseEntity.status(status).body(Map.of("status", "ERROR", "code", ex.code()));
    }

    @ExceptionHandler(RunnerRegistrationPort.RunnerAuthenticationException.class)
    public ResponseEntity<?> onRunnerAuthentication(
            RunnerRegistrationPort.RunnerAuthenticationException ex) {
        HttpStatus status = switch (ex.code()) {
            case "ELMOS_RUNNER_UNKNOWN" -> HttpStatus.NOT_FOUND;
            case "ELMOS_RUNNER_ENROLLMENT_REJECTED",
                 "ELMOS_RUNNER_NODE_TOKEN_REJECTED" -> HttpStatus.FORBIDDEN;
            case "ELMOS_RUNNER_ATTESTATION_INCOMPLETE",
                 "ELMOS_RUNNER_NOT_READY",
                 "ELMOS_RUNNER_NOT_ACTIVE" -> HttpStatus.PRECONDITION_FAILED;
            default -> HttpStatus.BAD_REQUEST;
        };
        return ResponseEntity.status(status)
                .body(Map.of("status", "ERROR", "code", ex.code()));
    }
}

@RestController
@RequestMapping("/api/v1/runner/nodes")
class RunnerFleetAdministrationController {
    private final RunnerRegistrationPort fleet;

    RunnerFleetAdministrationController(RunnerRegistrationPort fleet) {
        this.fleet = fleet;
    }

    record EnrollmentRequest(String poolId, Integer ttlSeconds) {
    }

    @PostMapping("/enrollments")
    ResponseEntity<?> issueEnrollment(@RequestBody EnrollmentRequest request) {
        ControlPlanePrincipal principal = principal("admin:operate");
        RunnerRegistrationPort.EnrollmentCredential credential = fleet.issueEnrollment(
                principal.organizationId(),
                request.poolId(),
                principal.actorId(),
                request.ttlSeconds() == null ? 900 : request.ttlSeconds());
        return ResponseEntity.status(HttpStatus.CREATED).body(Map.of(
                "credentialId", credential.credentialId(),
                "poolId", credential.poolId(),
                "enrollmentToken", credential.token(),
                "expiresAt", credential.expiresAt().toString(),
                "note", "The enrollment token is returned once and only its SHA-256 is stored."));
    }

    @DeleteMapping("/enrollments/{credentialId}")
    ResponseEntity<?> revokeEnrollment(@PathVariable String credentialId) {
        ControlPlanePrincipal principal = principal("admin:operate");
        fleet.revokeEnrollment(
                principal.organizationId(), credentialId, principal.actorId());
        return ResponseEntity.ok(Map.of(
                "status", "REVOKED", "credentialId", credentialId));
    }

    @PostMapping("/{runnerNodeId}/attestation/verify")
    ResponseEntity<?> verifyAttestation(@PathVariable String runnerNodeId) {
        ControlPlanePrincipal principal = principal("admin:approve");
        fleet.verifyAttestation(
                principal.organizationId(), runnerNodeId, principal.actorId());
        return ResponseEntity.ok(
                Map.of("status", "READY", "runnerNodeId", runnerNodeId));
    }

    @PostMapping("/{runnerNodeId}/drain")
    ResponseEntity<?> drain(@PathVariable String runnerNodeId) {
        ControlPlanePrincipal principal = principal("admin:operate");
        fleet.requestDrain(
                principal.organizationId(), runnerNodeId, principal.actorId());
        return ResponseEntity.accepted().body(
                Map.of("status", "DRAINING", "runnerNodeId", runnerNodeId));
    }

    private static ControlPlanePrincipal principal(String permission) {
        ControlPlanePrincipal principal = ControlPlanePrincipal.current()
                .orElseThrow(() -> new org.springframework.security.access.AccessDeniedException(
                        "CONTROL_PLANE_AUTH_REQUIRED"));
        principal.require(
                principal.organizationId(), principal.actorId(), permission);
        return principal;
    }

    @ExceptionHandler(RunnerRegistrationPort.RunnerAuthenticationException.class)
    ResponseEntity<?> onRunnerAuthentication(
            RunnerRegistrationPort.RunnerAuthenticationException ex) {
        HttpStatus status = switch (ex.code()) {
            case "ELMOS_RUNNER_UNKNOWN" -> HttpStatus.NOT_FOUND;
            case "ELMOS_RUNNER_ATTESTATION_INCOMPLETE",
                 "ELMOS_RUNNER_NOT_READY",
                 "ELMOS_RUNNER_NOT_ACTIVE" -> HttpStatus.PRECONDITION_FAILED;
            default -> HttpStatus.BAD_REQUEST;
        };
        return ResponseEntity.status(status)
                .body(Map.of("status", "ERROR", "code", ex.code()));
    }
}

/**
 * Lease reaper. One control-plane replica at a time holds the advisory lock, so
 * running three replicas does not triple-requeue anything.
 */
@RestController
class ExecutionLeaseReaper {

    private final ExecutionJobPort jobs;

    ExecutionLeaseReaper(ExecutionJobPort jobs) {
        this.jobs = jobs;
    }

    @Scheduled(fixedDelayString = "${elmos.execution.reaper-interval-ms:15000}")
    void reap() {
        jobs.reapExpiredLeases();
    }

    @GetMapping("/runner/v1/reaper/last-run")
    Map<String, Object> lastRun() {
        return Map.of("checkedAt", Instant.now().toString());
    }
}
