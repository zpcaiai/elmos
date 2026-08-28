package io.elmos.repair;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.MapperFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import io.elmos.repair.AgentRegistryModels.AgentDefinition;
import io.elmos.repair.AgentRegistryModels.AgentRegistryException;
import io.elmos.repair.AgentRegistryModels.AuditEvent;
import io.elmos.repair.AgentRegistryModels.LayerUpdate;
import io.elmos.repair.AgentRegistryModels.MutationResult;
import io.elmos.repair.AgentRegistryModels.RegistryMetrics;
import io.elmos.repair.AgentRegistryModels.RegistryRuntimeCapability;
import io.elmos.repair.AgentRegistryModels.RegistryView;
import io.elmos.repair.AgentRegistryModels.InvocationResult;
import io.elmos.repair.AgentRegistryModels.ResolvedAgent;
import io.elmos.repair.AgentRegistryModels.SelectionDecision;
import io.elmos.repair.AgentRegistryModels.SelectionPermit;
import io.elmos.repair.AgentRegistryModels.SelectionRequest;
import io.elmos.repair.AgentRegistryModels.Source;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.BasicFileAttributes;
import java.nio.file.attribute.PosixFilePermission;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Clock;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeMap;
import java.util.UUID;
import java.util.concurrent.locks.ReentrantLock;
import java.util.function.Function;

import static io.elmos.repair.AgentRegistryModels.CAPABILITY_VERSION;
import static io.elmos.repair.AgentRegistryModels.SCHEMA_VERSION;
import static io.elmos.repair.AgentRegistryModels.rejected;

/**
 * Tenant/project-scoped, file-backed Agent Registry with optimistic Context Epoch and durable idempotency.
 *
 * <p>The store is a local runtime boundary, not a provider executor. Agent selection produces an immutable,
 * short-lived permit and never invokes a model, command, repository mutation, or external service.</p>
 */
public final class DurableAgentRegistry {
    private static final String STORE_SCHEMA = "elmos.agent-registry.store.v1";
    private static final String ENVELOPE_SCHEMA = "elmos.agent-registry.envelope.v1";
    private static final String STATE_FILE = "registry.json";
    private static final String LOCK_FILE = "registry.lock";
    private static final int MAXIMUM_STATE_BYTES = 4 * 1024 * 1024;
    private static final int MAXIMUM_RECEIPTS = 2_048;
    private static final int MAXIMUM_AUDIT_EVENTS = 4_096;
    private static final ReentrantLock[] PROCESS_LOCKS = processLocks();
    private static final Set<PosixFilePermission> OWNER_DIRECTORY = Set.of(
            PosixFilePermission.OWNER_READ,
            PosixFilePermission.OWNER_WRITE,
            PosixFilePermission.OWNER_EXECUTE);
    private static final Set<PosixFilePermission> OWNER_FILE = Set.of(
            PosixFilePermission.OWNER_READ,
            PosixFilePermission.OWNER_WRITE);

    private final Path root;
    private final Clock clock;
    private final ObjectMapper json;

    public DurableAgentRegistry(Path root) {
        this(root, Clock.systemUTC());
    }

    DurableAgentRegistry(Path root, Clock clock) {
        Objects.requireNonNull(root, "root");
        if (!root.isAbsolute()) throw rejected("REGISTRY_ROOT_NOT_ABSOLUTE", "registry root must be absolute");
        this.clock = Objects.requireNonNull(clock, "clock");
        this.json = JsonMapper.builder()
                .addModule(new JavaTimeModule())
                .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
                .enable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS)
                .enable(MapperFeature.SORT_PROPERTIES_ALPHABETICALLY)
                .build();
        try {
            Files.createDirectories(root);
            requireDirectory(root, "REGISTRY_ROOT_INVALID");
            setOwnerOnly(root, OWNER_DIRECTORY);
            this.root = root.toRealPath(LinkOption.NOFOLLOW_LINKS);
        } catch (IOException error) {
            throw unavailable("REGISTRY_ROOT_UNAVAILABLE", error);
        }
    }

    public MutationResult replaceLayer(LayerUpdate request) {
        Objects.requireNonNull(request, "request");
        requirePermission(request.actorPermissions(), "agent-registry:write", "AGENT_REGISTRY_WRITE_REQUIRED");
        if (request.source() == Source.MANAGED) {
            requirePermission(request.actorPermissions(), "agent-registry:managed", "AGENT_REGISTRY_MANAGED_REQUIRED");
        }
        long started = System.nanoTime();
        String requestDigest = digest(request);
        return withLockedState(request.tenantId(), request.projectId(), state -> {
            MutationReceipt prior = state.mutationReceipts().get(request.idempotencyKey());
            if (prior != null) {
                requireSameDigest(prior.requestDigest(), requestDigest);
                RegistryMetrics replayMetrics = metrics(
                        state.metrics(), 0, 1, 0, 0, elapsedMicros(started), null);
                PersistedState replayState = state.withMetrics(replayMetrics);
                writeState(replayState);
                MutationResult result = prior.result();
                return new MutationResult(
                        result.status(), result.contextEpoch(), result.registryDigest(), true);
            }
            requireReceiptCapacity(state.mutationReceipts().size());
            if (request.expectedContextEpoch() != state.contextEpoch()) {
                throw rejected("CONTEXT_EPOCH_STALE", "configuration expected a stale Context Epoch");
            }

            Map<String, List<AgentDefinition>> layers = mutableLayers(state.layers());
            String layerName = request.source().name();
            boolean changed = !layers.get(layerName).equals(request.agents());
            layers.put(layerName, request.agents());
            long nextEpoch = changed ? Math.addExact(state.contextEpoch(), 1) : state.contextEpoch();
            String registryDigest = registryDigest(layers);
            String status = changed ? "updated" : "unchanged";
            MutationResult result = new MutationResult(status, nextEpoch, registryDigest, false);

            Map<String, MutationReceipt> receipts = new TreeMap<>(state.mutationReceipts());
            receipts.put(request.idempotencyKey(), new MutationReceipt(requestDigest, result));
            RegistryMetrics nextMetrics = metrics(
                    state.metrics(), changed ? 1 : 0, 0, 0, 0, elapsedMicros(started), null);
            List<AuditEvent> audit = appendAudit(
                    state.audit(), request.actorId(), "replace-layer", status, requestDigest,
                    registryDigest, nextEpoch);
            PersistedState next = new PersistedState(
                    STORE_SCHEMA, request.tenantId(), request.projectId(), nextEpoch,
                    layers, receipts, state.selectionReceipts(), nextMetrics, audit);
            writeState(next);
            return result;
        });
    }

    public SelectionDecision select(SelectionRequest request) {
        Objects.requireNonNull(request, "request");
        long started = System.nanoTime();
        String requestDigest = digest(request);
        return withLockedState(request.tenantId(), request.projectId(), state -> {
            SelectionReceipt prior = state.selectionReceipts().get(request.idempotencyKey());
            if (prior != null) {
                requireSameDigest(prior.requestDigest(), requestDigest);
                SelectionDecision result = prior.decision();
                SelectionDecision replay;
                String replayFailure = null;
                if (result.contextEpoch() != state.contextEpoch()) {
                    replayFailure = "CONTEXT_EPOCH_STALE";
                    replay = new SelectionDecision(
                            "denied", replayFailure, state.contextEpoch(), registryDigest(state.layers()),
                            null, true);
                } else if (result.permit() != null && !result.permit().expiresAt().isAfter(clock.instant())) {
                    replayFailure = "AGENT_SELECTION_PERMIT_EXPIRED";
                    replay = new SelectionDecision(
                            "denied", replayFailure, state.contextEpoch(), registryDigest(state.layers()),
                            null, true);
                } else {
                    replay = new SelectionDecision(
                            result.status(), result.reasonCode(), result.contextEpoch(),
                            result.registryDigest(), result.permit(), true);
                }
                RegistryMetrics replayMetrics = metrics(
                        state.metrics(), 0, 0, 0, replayFailure == null ? 0 : 1,
                        elapsedMicros(started), replayFailure);
                List<AuditEvent> replayAudit = replayFailure == null
                        ? state.audit()
                        : appendAudit(
                                state.audit(), request.actorId(), "select-agent-replay", replayFailure,
                                requestDigest, replay.registryDigest(), state.contextEpoch());
                writeState(new PersistedState(
                        STORE_SCHEMA, state.tenantId(), state.projectId(), state.contextEpoch(),
                        state.layers(), state.mutationReceipts(), state.selectionReceipts(),
                        replayMetrics, replayAudit));
                return replay;
            }
            requireReceiptCapacity(state.selectionReceipts().size());
            Map<String, ResolvedAgent> agents = resolve(state.layers());
            String registryDigest = registryDigest(state.layers());
            SelectionDecision decision = decide(request, state.contextEpoch(), registryDigest, agents);
            String failure = decision.allowed() ? null : decision.reasonCode();
            RegistryMetrics nextMetrics = metrics(
                    state.metrics(), 0, 0, decision.allowed() ? 1 : 0, decision.allowed() ? 0 : 1,
                    elapsedMicros(started), failure);
            Map<String, SelectionReceipt> receipts = new TreeMap<>(state.selectionReceipts());
            receipts.put(request.idempotencyKey(), new SelectionReceipt(requestDigest, decision));
            List<AuditEvent> audit = appendAudit(
                    state.audit(), request.actorId(), "select-agent", decision.reasonCode(), requestDigest,
                    registryDigest, state.contextEpoch());
            PersistedState next = new PersistedState(
                    STORE_SCHEMA, request.tenantId(), request.projectId(), state.contextEpoch(),
                    state.layers(), state.mutationReceipts(), receipts, nextMetrics, audit);
            writeState(next);
            return decision;
        });
    }

    /**
     * Revalidates an allowed selection against the current durable Context Epoch immediately before invoking
     * a bounded in-process admission callback. The callback runs inside the registry lock and therefore must
     * not perform external I/O, call back into this registry, or outlive the selected agent's timeout.
     */
    public <T> InvocationResult<T> invokeSelected(
            SelectionDecision decision,
            Function<SelectionPermit, T> admissionCallback
    ) {
        Objects.requireNonNull(decision, "decision");
        Objects.requireNonNull(admissionCallback, "admissionCallback");
        if (!decision.allowed()) {
            throw rejected(decision.reasonCode(), "agent selection was denied before callback invocation");
        }
        SelectionPermit permit = decision.permit();
        if (decision.contextEpoch() != permit.contextEpoch()
                || !constantTimeEquals(decision.registryDigest(), permit.registryDigest())) {
            throw rejected("AGENT_SELECTION_PERMIT_INVALID", "selection decision and permit are inconsistent");
        }
        return withLockedState(permit.tenantId(), permit.projectId(), state -> {
            Instant now = clock.instant();
            if (!permit.expiresAt().isAfter(now)) {
                throw rejected(
                        "AGENT_SELECTION_PERMIT_EXPIRED",
                        "agent selection permit expired before callback invocation");
            }
            String currentRegistryDigest = registryDigest(state.layers());
            if (permit.contextEpoch() != state.contextEpoch()
                    || !constantTimeEquals(permit.registryDigest(), currentRegistryDigest)) {
                throw rejected("CONTEXT_EPOCH_STALE", "agent selection permit belongs to a stale Context Epoch");
            }
            if (!constantTimeEquals(permit.permitDigest(), permitDigest(permit))) {
                throw rejected("AGENT_SELECTION_PERMIT_INVALID", "agent selection permit digest is invalid");
            }
            if (!matchesDurableSelectionReceipt(state, permit)) {
                throw rejected(
                        "AGENT_SELECTION_PERMIT_UNRECOGNIZED",
                        "agent selection permit has no matching durable selection receipt");
            }
            ResolvedAgent current = resolve(state.layers()).get(permit.agentId());
            if (current == null
                    || !current.definition().enabled()
                    || current.source() != permit.source()
                    || current.definition().version() != permit.agentVersion()
                    || !current.definition().permissions().containsAll(permit.permissions())
                    || !current.definition().capabilities().containsAll(permit.capabilities())
                    || !current.definition().limits().equals(permit.limits())) {
                throw rejected("AGENT_SELECTION_STALE", "selected agent no longer matches the current registry");
            }
            return new InvocationResult<>(permit, admissionCallback.apply(permit));
        });
    }

    public RegistryRuntimeCapability capability() {
        return new RegistryRuntimeCapability(
                SCHEMA_VERSION,
                CAPABILITY_VERSION,
                "agent-registry",
                "LOCAL_RUNTIME_IMPLEMENTED",
                Set.of("audit", "capability", "invoke-selected", "replace-layer", "select", "view"),
                Set.of(
                        "agent-registry:audit",
                        "agent-registry:managed",
                        "agent-registry:read",
                        "agent-registry:select",
                        "agent-registry:write"),
                false,
                "NOT_RUN",
                "NOT_CERTIFIED");
    }

    public RegistryView view(String tenantId, String projectId, Set<String> actorPermissions) {
        String tenant = AgentRegistryModels.identifier(tenantId, "tenantId");
        String project = AgentRegistryModels.identifier(projectId, "projectId");
        requirePermission(actorPermissions, "agent-registry:read", "AGENT_REGISTRY_READ_REQUIRED");
        return withLockedState(tenant, project, state -> {
            Map<String, ResolvedAgent> resolved = resolve(state.layers());
            return new RegistryView(
                    SCHEMA_VERSION,
                    CAPABILITY_VERSION,
                    tenant,
                    project,
                    state.contextEpoch(),
                    registryDigest(state.layers()),
                    List.copyOf(resolved.values()),
                    state.metrics());
        });
    }

    public List<AuditEvent> audit(String tenantId, String projectId, Set<String> actorPermissions) {
        String tenant = AgentRegistryModels.identifier(tenantId, "tenantId");
        String project = AgentRegistryModels.identifier(projectId, "projectId");
        requirePermission(actorPermissions, "agent-registry:audit", "AGENT_REGISTRY_AUDIT_REQUIRED");
        return withLockedState(tenant, project, state -> List.copyOf(state.audit()));
    }

    private SelectionDecision decide(
            SelectionRequest request,
            long contextEpoch,
            String registryDigest,
            Map<String, ResolvedAgent> agents
    ) {
        String reason = null;
        ResolvedAgent resolved = agents.get(request.agentId());
        if (!request.actorPermissions().contains("agent-registry:select")) {
            reason = "AGENT_REGISTRY_SELECT_REQUIRED";
        } else if (request.expectedContextEpoch() != contextEpoch) {
            reason = "CONTEXT_EPOCH_STALE";
        } else if (resolved == null) {
            reason = "AGENT_NOT_FOUND";
        } else if (!resolved.definition().enabled()) {
            reason = "AGENT_DISABLED";
        } else if (!resolved.definition().permissions().containsAll(request.requiredPermissions())) {
            reason = "AGENT_PERMISSION_NOT_DECLARED";
        } else if (!request.actorPermissions().containsAll(request.requiredPermissions())) {
            reason = "ACTOR_PERMISSION_DENIED";
        } else if (!resolved.definition().capabilities().containsAll(request.requiredCapabilities())) {
            reason = "AGENT_CAPABILITY_UNAVAILABLE";
        }
        if (reason != null) {
            return new SelectionDecision("denied", reason, contextEpoch, registryDigest, null, false);
        }

        Instant issuedAt = clock.instant();
        Instant expiresAt = issuedAt.plusMillis(resolved.definition().limits().timeoutMillis());
        SelectionPermit unsignedPermit = new SelectionPermit(
                request.tenantId(), request.projectId(), request.actorId(), resolved.definition().id(),
                resolved.source(), resolved.definition().version(), contextEpoch,
                request.requiredPermissions(), request.requiredCapabilities(), resolved.definition().limits(),
                issuedAt, expiresAt, registryDigest, "0".repeat(64));
        SelectionPermit permit = new SelectionPermit(
                unsignedPermit.tenantId(), unsignedPermit.projectId(), unsignedPermit.actorId(),
                unsignedPermit.agentId(), unsignedPermit.source(), unsignedPermit.agentVersion(),
                unsignedPermit.contextEpoch(), unsignedPermit.permissions(), unsignedPermit.capabilities(),
                unsignedPermit.limits(), unsignedPermit.issuedAt(), unsignedPermit.expiresAt(),
                unsignedPermit.registryDigest(), permitDigest(unsignedPermit));
        return new SelectionDecision("allowed", "AGENT_SELECTION_ALLOWED", contextEpoch,
                registryDigest, permit, false);
    }

    private <T> T withLockedState(String tenantId, String projectId, StateOperation<T> operation) {
        Path scope = scope(tenantId, projectId);
        Path lockPath = scope.resolve(LOCK_FILE);
        ReentrantLock processLock = PROCESS_LOCKS[Math.floorMod(scope.hashCode(), PROCESS_LOCKS.length)];
        processLock.lock();
        try {
            if (!Files.exists(lockPath, LinkOption.NOFOLLOW_LINKS)) {
                createLockFile(lockPath);
            }
            requireRegularSingleLink(lockPath, "REGISTRY_LOCK_INVALID");
            try (FileChannel channel = FileChannel.open(lockPath, StandardOpenOption.WRITE);
                 FileLock ignored = channel.lock()) {
                requireRegularSingleLink(lockPath, "REGISTRY_LOCK_INVALID");
                OperationScope current = new OperationScope(scope, tenantId, projectId);
                OPERATION_SCOPE.set(current);
                try {
                    return operation.apply(readState(scope, tenantId, projectId));
                } finally {
                    OPERATION_SCOPE.remove();
                }
            }
        } catch (AgentRegistryException error) {
            throw error;
        } catch (IOException error) {
            throw unavailable("REGISTRY_STORE_UNAVAILABLE", error);
        } finally {
            processLock.unlock();
        }
    }

    private static final ThreadLocal<OperationScope> OPERATION_SCOPE = new ThreadLocal<>();

    private PersistedState readState(Path scope, String tenantId, String projectId) {
        Path statePath = scope.resolve(STATE_FILE);
        if (!Files.exists(statePath, LinkOption.NOFOLLOW_LINKS)) return emptyState(tenantId, projectId);
        requireRegularSingleLink(statePath, "REGISTRY_STATE_INVALID");
        try {
            long size = Files.size(statePath);
            if (size < 2 || size > MAXIMUM_STATE_BYTES) {
                throw rejected("REGISTRY_STATE_SIZE_INVALID", "registry state size is outside the bounded range");
            }
            byte[] bytes = readStableBytes(statePath, size);
            Envelope envelope = json.readValue(bytes, Envelope.class);
            if (!ENVELOPE_SCHEMA.equals(envelope.schemaVersion()) || envelope.payload() == null) {
                throw rejected("REGISTRY_STATE_SCHEMA_INVALID", "registry state envelope schema is invalid");
            }
            String expected = digest(envelope.payload());
            if (!MessageDigest.isEqual(
                    expected.getBytes(StandardCharsets.US_ASCII),
                    String.valueOf(envelope.payloadDigest()).getBytes(StandardCharsets.US_ASCII))) {
                throw rejected("REGISTRY_STATE_TAMPERED", "registry state digest does not match its payload");
            }
            validateState(envelope.payload(), tenantId, projectId);
            return envelope.payload();
        } catch (JsonProcessingException error) {
            throw unavailable("REGISTRY_STATE_JSON_INVALID", error);
        } catch (IOException error) {
            throw unavailable("REGISTRY_STATE_UNAVAILABLE", error);
        }
    }

    private void writeState(PersistedState state) {
        OperationScope operation = OPERATION_SCOPE.get();
        requireOperationScope(operation, state.tenantId(), state.projectId());
        validateState(state, operation.tenantId(), operation.projectId());
        Envelope envelope = new Envelope(ENVELOPE_SCHEMA, state, digest(state));
        byte[] bytes = serialize(json, envelope, "REGISTRY_STATE_SERIALIZATION_FAILED");
        if (bytes.length > MAXIMUM_STATE_BYTES) {
            throw rejected("REGISTRY_STATE_SIZE_INVALID", "registry state exceeds the bounded byte limit");
        }
        Path candidate = operation.scope().resolve("registry-" + UUID.randomUUID() + ".tmp");
        Path target = operation.scope().resolve(STATE_FILE);
        writeCandidate(candidate, bytes);
        commitCandidate(candidate, target, operation.scope());
    }

    static void writeCandidate(Path candidate, byte[] bytes) {
        try (FileChannel output = FileChannel.open(
                candidate, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)) {
            setOwnerOnly(candidate, OWNER_FILE);
            ByteBuffer buffer = ByteBuffer.wrap(bytes);
            while (buffer.hasRemaining()) output.write(buffer);
            output.force(true);
        } catch (IOException error) {
            deleteCandidate(candidate);
            throw unavailable("REGISTRY_STATE_WRITE_FAILED", error);
        }
    }

    private static void commitCandidate(Path candidate, Path target, Path scope) {
        commitCandidate(
                candidate,
                target,
                scope,
                (source, destination) -> Files.move(
                        source, destination, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING));
    }

    static void commitCandidate(Path candidate, Path target, Path scope, AtomicMover mover) {
        try {
            requireRegularSingleLink(candidate, "REGISTRY_STATE_CANDIDATE_INVALID");
            mover.move(candidate, target);
            syncDirectory(scope);
            requireRegularSingleLink(target, "REGISTRY_STATE_INVALID");
        } catch (AtomicMoveNotSupportedException error) {
            deleteCandidate(candidate);
            throw unavailable("REGISTRY_ATOMIC_MOVE_REQUIRED", error);
        } catch (IOException error) {
            deleteCandidate(candidate);
            throw unavailable("REGISTRY_STATE_COMMIT_FAILED", error);
        }
    }

    private Path scope(String tenantId, String projectId) {
        String tenant = AgentRegistryModels.identifier(tenantId, "tenantId");
        String project = AgentRegistryModels.identifier(projectId, "projectId");
        Path tenantRoot = root.resolve("tenant-" + sha256(tenant).substring(0, 32));
        Path projectRoot = tenantRoot.resolve("project-" + sha256(project).substring(0, 32));
        try {
            createPrivateDirectory(tenantRoot);
            createPrivateDirectory(projectRoot);
            Path realProjectRoot = projectRoot.toRealPath(LinkOption.NOFOLLOW_LINKS);
            requireContainedScope(root, realProjectRoot);
            return realProjectRoot;
        } catch (IOException error) {
            throw unavailable("REGISTRY_SCOPE_UNAVAILABLE", error);
        }
    }

    private void createPrivateDirectory(Path path) throws IOException {
        try {
            Files.createDirectory(path);
        } catch (java.nio.file.FileAlreadyExistsException ignored) {
            // The existing path is validated below without following links.
        }
        requireDirectory(path, "REGISTRY_SCOPE_INVALID");
        setOwnerOnly(path, OWNER_DIRECTORY);
    }

    static void requireDirectory(Path path, String code) throws IOException {
        BasicFileAttributes attributes = Files.readAttributes(
                path, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
        if (attributes.isSymbolicLink() || !attributes.isDirectory()) {
            throw rejected(code, "registry path must be a non-symlink directory");
        }
    }

    static void requireRegularSingleLink(Path path, String code) {
        try {
            BasicFileAttributes attributes = Files.readAttributes(
                    path, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
            if (attributes.isSymbolicLink() || !attributes.isRegularFile()) {
                throw rejected(code, "registry path must be a non-symlink regular file");
            }
            try {
                Object links = Files.getAttribute(path, "unix:nlink", LinkOption.NOFOLLOW_LINKS);
                requireSingleLinkCount(links, code);
            } catch (UnsupportedOperationException ignored) {
                // The exact platform does not expose nlink; all other no-follow checks remain active.
            }
        } catch (IOException error) {
            throw unavailable(code, error);
        }
    }

    static void setOwnerOnly(Path path, Set<PosixFilePermission> permissions) throws IOException {
        try {
            Files.setPosixFilePermissions(path, permissions);
        } catch (UnsupportedOperationException ignored) {
            // Windows/non-POSIX filesystems rely on the enclosing deployment ACL.
        }
    }

    private static void syncDirectory(Path directory) throws IOException {
        try (FileChannel channel = FileChannel.open(directory, StandardOpenOption.READ)) {
            channel.force(true);
        }
    }

    static void deleteCandidate(Path candidate) {
        if (candidate == null) return;
        try {
            if (Files.isRegularFile(candidate, LinkOption.NOFOLLOW_LINKS)) Files.deleteIfExists(candidate);
        } catch (IOException ignored) {
            // A non-deleted private candidate is visible to recovery inventory and is never adopted.
        }
    }

    static void createLockFile(Path lockPath) throws IOException {
        try {
            Files.createFile(lockPath);
            setOwnerOnly(lockPath, OWNER_FILE);
        } catch (java.nio.file.FileAlreadyExistsException ignored) {
            // A concurrent process created the exact lock file.
        }
    }

    static byte[] readStableBytes(Path statePath, long expectedSize) throws IOException {
        byte[] bytes = Files.readAllBytes(statePath);
        if (bytes.length != expectedSize) {
            throw rejected("REGISTRY_STATE_CHANGED", "registry state changed while reading");
        }
        return bytes;
    }

    static byte[] serialize(ObjectMapper mapper, Object value, String failureCode) {
        try {
            return mapper.writeValueAsBytes(value);
        } catch (JsonProcessingException error) {
            throw unavailable(failureCode, error);
        }
    }

    static void requireOperationScope(OperationScope operation, String tenantId, String projectId) {
        if (operation == null
                || !operation.tenantId().equals(tenantId)
                || !operation.projectId().equals(projectId)) {
            throw rejected("REGISTRY_OPERATION_SCOPE_INVALID", "registry write escaped its locked scope");
        }
    }

    static void requireContainedScope(Path root, Path candidate) {
        if (!candidate.startsWith(root)) {
            throw rejected("REGISTRY_SCOPE_ESCAPED", "registry scope escaped its configured root");
        }
    }

    static void requireSingleLinkCount(Object links, String code) {
        if (!(links instanceof Number number) || number.longValue() != 1L) {
            throw rejected(code, "registry file must have exactly one hard link");
        }
    }

    private void validateState(PersistedState state, String tenantId, String projectId) {
        if (!STORE_SCHEMA.equals(state.schemaVersion())
                || !tenantId.equals(state.tenantId())
                || !projectId.equals(state.projectId())
                || state.contextEpoch() < 0) {
            throw rejected("REGISTRY_STATE_SCOPE_INVALID", "registry state does not match its exact scope");
        }
        if (!state.layers().keySet().equals(Set.of("GLOBAL", "PROJECT", "MANAGED"))) {
            throw rejected("REGISTRY_STATE_LAYERS_INVALID", "registry state must contain the three exact layers");
        }
        state.layers().forEach((source, agents) -> {
            if (agents.size() > 256) {
                throw rejected("REGISTRY_STATE_LAYERS_INVALID", "registry layer is invalid");
            }
            String previous = null;
            for (AgentDefinition agent : agents) {
                if (agent == null || (previous != null && previous.compareTo(agent.id()) >= 0)) {
                    throw rejected("REGISTRY_STATE_LAYERS_INVALID", "registry layer order or identity is invalid");
                }
                previous = agent.id();
            }
        });
        if (state.mutationReceipts().size() > MAXIMUM_RECEIPTS
                || state.selectionReceipts().size() > MAXIMUM_RECEIPTS
                || state.audit().size() > MAXIMUM_AUDIT_EVENTS) {
            throw rejected("REGISTRY_STATE_CAPACITY_INVALID", "registry state exceeds its bounded capacity");
        }
        state.mutationReceipts().forEach((key, receipt) -> {
            AgentRegistryModels.identifier(key, "mutation receipt key");
            if (receipt.result() == null) {
                throw rejected("REGISTRY_RECEIPT_INVALID", "mutation receipt is incomplete");
            }
            AgentRegistryModels.digest(receipt.requestDigest(), "mutation receipt requestDigest");
            if (!Set.of("updated", "unchanged").contains(receipt.result().status())
                    || receipt.result().contextEpoch() > state.contextEpoch()) {
                throw rejected("REGISTRY_RECEIPT_INVALID", "mutation receipt result is invalid");
            }
        });
        state.selectionReceipts().forEach((key, receipt) -> {
            AgentRegistryModels.identifier(key, "selection receipt key");
            if (receipt.decision() == null) {
                throw rejected("REGISTRY_RECEIPT_INVALID", "selection receipt is incomplete");
            }
            AgentRegistryModels.digest(receipt.requestDigest(), "selection receipt requestDigest");
            SelectionDecision decision = receipt.decision();
            if (!Set.of("allowed", "denied").contains(decision.status())
                    || decision.contextEpoch() > state.contextEpoch()) {
                throw rejected("REGISTRY_RECEIPT_INVALID", "selection receipt decision is invalid");
            }
            if (decision.permit() != null) validateStoredPermit(decision, tenantId, projectId);
        });
        for (int index = 0; index < state.audit().size(); index++) {
            if (state.audit().get(index).sequence() != index + 1L) {
                throw rejected("REGISTRY_AUDIT_SEQUENCE_INVALID", "registry audit sequence is not contiguous");
            }
        }
        Objects.requireNonNull(state.metrics(), "state.metrics");
    }

    private static PersistedState emptyState(String tenantId, String projectId) {
        Map<String, List<AgentDefinition>> layers = new TreeMap<>();
        for (Source source : Source.values()) layers.put(source.name(), List.of());
        return new PersistedState(
                STORE_SCHEMA, tenantId, projectId, 0, layers, Map.of(), Map.of(),
                new RegistryMetrics(0, 0, 0, 0, 0, Map.of()), List.of());
    }

    private static Map<String, List<AgentDefinition>> mutableLayers(
            Map<String, List<AgentDefinition>> layers
    ) {
        Map<String, List<AgentDefinition>> copy = new TreeMap<>();
        layers.forEach((source, agents) -> copy.put(source, List.copyOf(agents)));
        return copy;
    }

    private static Map<String, ResolvedAgent> resolve(Map<String, List<AgentDefinition>> layers) {
        Map<String, ResolvedAgent> resolved = new TreeMap<>();
        List<Source> sources = new ArrayList<>(List.of(Source.values()));
        sources.sort(Comparator.comparingInt(Source::precedence));
        for (Source source : sources) {
            for (AgentDefinition definition : layers.get(source.name())) {
                resolved.put(definition.id(), new ResolvedAgent(definition, source));
            }
        }
        return resolved;
    }

    private String registryDigest(Map<String, List<AgentDefinition>> layers) {
        return digest(resolve(layers));
    }

    private String permitDigest(SelectionPermit permit) {
        Map<String, Object> document = new LinkedHashMap<>();
        document.put("actorId", permit.actorId());
        document.put("agentId", permit.agentId());
        document.put("agentVersion", permit.agentVersion());
        document.put("capabilities", permit.capabilities());
        document.put("contextEpoch", permit.contextEpoch());
        document.put("expiresAt", permit.expiresAt().toString());
        document.put("issuedAt", permit.issuedAt().toString());
        document.put("permissions", permit.permissions());
        document.put("projectId", permit.projectId());
        document.put("registryDigest", permit.registryDigest());
        document.put("source", permit.source().name());
        document.put("tenantId", permit.tenantId());
        return digest(document);
    }

    private void validateStoredPermit(
            SelectionDecision decision,
            String tenantId,
            String projectId
    ) {
        SelectionPermit permit = decision.permit();
        if (!tenantId.equals(permit.tenantId())
                || !projectId.equals(permit.projectId())
                || decision.contextEpoch() != permit.contextEpoch()
                || !constantTimeEquals(decision.registryDigest(), permit.registryDigest())
                || !constantTimeEquals(permit.permitDigest(), permitDigest(permit))) {
            throw rejected("REGISTRY_RECEIPT_INVALID", "stored selection permit is invalid");
        }
    }

    private static boolean matchesDurableSelectionReceipt(PersistedState state, SelectionPermit permit) {
        return state.selectionReceipts().values().stream().anyMatch(receipt -> {
            SelectionDecision persisted = receipt.decision();
            SelectionPermit persistedPermit = persisted.permit();
            return persisted.allowed()
                    && constantTimeEquals(persistedPermit.permitDigest(), permit.permitDigest())
                    && persistedPermit.equals(permit);
        });
    }

    private String digest(Object value) {
        return sha256(serialize(json, value, "REGISTRY_DIGEST_SERIALIZATION_FAILED"));
    }

    private static String sha256(String value) {
        return sha256(value.getBytes(StandardCharsets.UTF_8));
    }

    private static String sha256(byte[] value) {
        return sha256(value, "SHA-256");
    }

    static String sha256(byte[] value, String algorithm) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance(algorithm).digest(value));
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException("SHA-256 is unavailable", error);
        }
    }

    private static RegistryMetrics metrics(
            RegistryMetrics current,
            long configurationChanges,
            long configurationReplays,
            long allowedSelections,
            long deniedSelections,
            long elapsedMicros,
            String failureType
    ) {
        Map<String, Long> failures = new TreeMap<>(current.failureTypes());
        if (failureType != null) failures.merge(failureType, 1L, Math::addExact);
        return new RegistryMetrics(
                Math.addExact(current.configurationChanges(), configurationChanges),
                Math.addExact(current.configurationReplays(), configurationReplays),
                Math.addExact(current.allowedSelections(), allowedSelections),
                Math.addExact(current.deniedSelections(), deniedSelections),
                Math.addExact(current.totalWallClockMicros(), elapsedMicros),
                failures);
    }

    private List<AuditEvent> appendAudit(
            List<AuditEvent> current,
            String actorId,
            String operation,
            String outcome,
            String requestDigest,
            String registryDigest,
            long contextEpoch
    ) {
        if (current.size() >= MAXIMUM_AUDIT_EVENTS) {
            throw rejected("REGISTRY_AUDIT_CAPACITY_EXHAUSTED", "registry audit capacity is exhausted");
        }
        List<AuditEvent> next = new ArrayList<>(current);
        next.add(new AuditEvent(
                current.size() + 1L, clock.instant(), actorId, operation, outcome,
                requestDigest, registryDigest, contextEpoch));
        return List.copyOf(next);
    }

    private static void requirePermission(Set<String> permissions, String required, String code) {
        Objects.requireNonNull(permissions, "permissions");
        if (!permissions.contains(required)) throw rejected(code, "required registry permission is missing");
    }

    private static void requireSameDigest(String expected, String actual) {
        if (!constantTimeEquals(expected, actual)) {
            throw rejected("IDEMPOTENCY_KEY_CONFLICT", "idempotency key was reused with different input");
        }
    }

    static boolean constantTimeEquals(String expected, String actual) {
        return expected != null && actual != null && MessageDigest.isEqual(
                expected.getBytes(StandardCharsets.US_ASCII), actual.getBytes(StandardCharsets.US_ASCII));
    }

    private static void requireReceiptCapacity(int size) {
        if (size >= MAXIMUM_RECEIPTS) {
            throw rejected("REGISTRY_RECEIPT_CAPACITY_EXHAUSTED", "registry receipt capacity is exhausted");
        }
    }

    private static long elapsedMicros(long started) {
        return Math.max(0L, (System.nanoTime() - started) / 1_000L);
    }

    private static ReentrantLock[] processLocks() {
        ReentrantLock[] locks = new ReentrantLock[64];
        for (int index = 0; index < locks.length; index++) locks[index] = new ReentrantLock(true);
        return locks;
    }

    private static AgentRegistryException unavailable(String code, Exception error) {
        return new AgentRegistryException(code, "durable Agent Registry operation failed: " + error.getClass().getSimpleName());
    }

    @FunctionalInterface
    private interface StateOperation<T> {
        T apply(PersistedState state);
    }

    @FunctionalInterface
    interface AtomicMover {
        void move(Path source, Path target) throws IOException;
    }

    private record Envelope(String schemaVersion, PersistedState payload, String payloadDigest) {}

    private record MutationReceipt(String requestDigest, MutationResult result) {}

    private record SelectionReceipt(String requestDigest, SelectionDecision decision) {}

    static record OperationScope(Path scope, String tenantId, String projectId) {}

    private record PersistedState(
            String schemaVersion,
            String tenantId,
            String projectId,
            long contextEpoch,
            Map<String, List<AgentDefinition>> layers,
            Map<String, MutationReceipt> mutationReceipts,
            Map<String, SelectionReceipt> selectionReceipts,
            RegistryMetrics metrics,
            List<AuditEvent> audit
    ) {
        private PersistedState {
            schemaVersion = Objects.requireNonNull(schemaVersion, "schemaVersion");
            tenantId = Objects.requireNonNull(tenantId, "tenantId");
            projectId = Objects.requireNonNull(projectId, "projectId");
            layers = Map.copyOf(new TreeMap<>(Objects.requireNonNull(layers, "layers")));
            mutationReceipts = Map.copyOf(new TreeMap<>(
                    Objects.requireNonNull(mutationReceipts, "mutationReceipts")));
            selectionReceipts = Map.copyOf(new TreeMap<>(
                    Objects.requireNonNull(selectionReceipts, "selectionReceipts")));
            metrics = Objects.requireNonNull(metrics, "metrics");
            audit = List.copyOf(Objects.requireNonNull(audit, "audit"));
        }

        private PersistedState withMetrics(RegistryMetrics nextMetrics) {
            return new PersistedState(
                    schemaVersion, tenantId, projectId, contextEpoch, layers,
                    mutationReceipts, selectionReceipts, nextMetrics, audit);
        }
    }
}
