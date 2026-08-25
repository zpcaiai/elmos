package io.elmos.cas;

import java.io.ByteArrayOutputStream;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.LongSupplier;

/**
 * ELMOS-CAS-007 through ELMOS-CAS-011. Direct and multipart upload with resume.
 *
 * <p>The contract that makes resume safe is per-chunk digests. Without them a client that
 * reconnects can only say "I sent 900 MB"; the server has to believe it, and a proxy that
 * silently truncated one chunk in the middle produces an object that assembles to a wrong final
 * digest after the whole transfer is spent - or worse, to a right-looking one if the final
 * digest is also client supplied. Every chunk is verified on arrival, and the final digest is
 * recomputed from the assembled bytes before anything is accepted (ELMOS-CAS-009).
 *
 * <p>Chunks are idempotent by index: re-sending an identical chunk is an ack, re-sending a
 * <em>different</em> chunk under the same index is a conflict and is refused. A retrying client
 * must never be able to rewrite history in a half-finished object.
 */
public final class ResumableUploadService {

    public enum ChunkStatus {
        ACCEPTED,
        DUPLICATE_IDENTICAL,
        REJECTED_DIGEST_MISMATCH,
        REJECTED_CONFLICT,
        REJECTED_RANGE,
        REJECTED_SESSION_CLOSED,
        REJECTED_EXPIRED
    }

    public enum SessionState {
        OPEN,
        COMPLETED,
        ABORTED,
        QUARANTINED,
        EXPIRED
    }

    public record ChunkAck(int index, ChunkStatus status, long resumeOffset, long throttleDelayMillis, String detail) {
        public boolean accepted() {
            return status == ChunkStatus.ACCEPTED || status == ChunkStatus.DUPLICATE_IDENTICAL;
        }
    }

    public record CompletedUpload(CasDigest digest, long bytes, int chunks, boolean alreadyPresent) {
    }

    public record QuarantineRecord(String quarantineId, String sessionId, String tenantId, CasDigest declared,
                                   CasDigest actual, long atEpochMillis) {
    }

    private final CasStore store;
    private final LongSupplier clock;
    private final TransferPolicy.ChunkCodec codec = new TransferPolicy.ChunkCodec();
    private final Map<String, Session> sessions = new ConcurrentHashMap<>();
    private final List<QuarantineRecord> quarantine = Collections.synchronizedList(new ArrayList<>());

    public ResumableUploadService(CasStore store, LongSupplier clock) {
        this.store = store;
        this.clock = clock;
    }

    /**
     * ELMOS-CAS-007 direct upload for small blobs: one call, no session, still digest verified.
     *
     * @return {@code alreadyPresent} true when the store deduplicated the write (ELMOS-CAS-011)
     */
    public CompletedUpload uploadDirect(String tenantId, CasDigest declared, byte[] content) {
        CasText.required(tenantId, "tenantId");
        CasDigest actual = CasDigest.of(content);
        if (!actual.equals(declared)) {
            String quarantineId = quarantine(null, tenantId, declared, actual);
            throw new CasExceptions.CasQuarantinedException(quarantineId,
                    "direct upload hashed to " + actual.compact());
        }
        boolean present = store.contains(declared);
        if (!present) {
            store.put(declared, content);
        }
        return new CompletedUpload(declared, content.length, 1, present);
    }

    public Session open(String sessionId, String tenantId, long declaredSize, int chunkSize,
                        Optional<CasDigest> declaredDigest, long ttlMillis,
                        TransferPolicy.BandwidthLimiter limiter) {
        CasText.required(sessionId, "sessionId");
        CasText.required(tenantId, "tenantId");
        CasText.requirePositive(chunkSize, "chunkSize");
        if (declaredSize < 0) {
            throw new IllegalArgumentException("declaredSize must not be negative");
        }
        declaredDigest.ifPresent(digest -> {
            if (digest.sizeBytes() != declaredSize) {
                throw new IllegalArgumentException("declared digest size " + digest.sizeBytes()
                        + " contradicts declared upload size " + declaredSize);
            }
        });
        Session session = new Session(sessionId, tenantId, declaredSize, chunkSize, declaredDigest,
                clock.getAsLong(), clock.getAsLong() + ttlMillis, limiter);
        if (sessions.putIfAbsent(sessionId, session) != null) {
            throw new IllegalStateException("upload session already exists: " + sessionId);
        }
        return session;
    }

    public Optional<Session> session(String sessionId) {
        return Optional.ofNullable(sessions.get(sessionId));
    }

    /** ELMOS-CAS-038. Sessions that neither completed nor aborted before their deadline. */
    public List<Session> incompleteSessions() {
        long now = clock.getAsLong();
        List<Session> incomplete = new ArrayList<>();
        for (Session session : sessions.values()) {
            if (session.state == SessionState.OPEN && now > session.deadlineEpochMillis) {
                session.state = SessionState.EXPIRED;
            }
            if (session.state == SessionState.EXPIRED || (session.state == SessionState.OPEN && !session.complete())) {
                incomplete.add(session);
            }
        }
        incomplete.sort((left, right) -> left.sessionId.compareTo(right.sessionId));
        return List.copyOf(incomplete);
    }

    public List<QuarantineRecord> quarantined() {
        synchronized (quarantine) {
            return List.copyOf(quarantine);
        }
    }

    private String quarantine(String sessionId, String tenantId, CasDigest declared, CasDigest actual) {
        String quarantineId = "q-" + declared.hex().substring(0, 16) + "-" + actual.hex().substring(0, 16);
        quarantine.add(new QuarantineRecord(quarantineId, sessionId, tenantId, declared, actual, clock.getAsLong()));
        return quarantineId;
    }

    /** One multipart upload. Single-writer per session; the service owns the session registry. */
    public final class Session {

        private final String sessionId;
        private final String tenantId;
        private final long declaredSize;
        private final int chunkSize;
        private final Optional<CasDigest> declaredDigest;
        private final long createdEpochMillis;
        private final long deadlineEpochMillis;
        private final TransferPolicy.BandwidthLimiter limiter;
        private final TreeMap<Integer, byte[]> chunks = new TreeMap<>();
        private SessionState state = SessionState.OPEN;

        private Session(String sessionId, String tenantId, long declaredSize, int chunkSize,
                        Optional<CasDigest> declaredDigest, long createdEpochMillis, long deadlineEpochMillis,
                        TransferPolicy.BandwidthLimiter limiter) {
            this.sessionId = sessionId;
            this.tenantId = tenantId;
            this.declaredSize = declaredSize;
            this.chunkSize = chunkSize;
            this.declaredDigest = declaredDigest;
            this.createdEpochMillis = createdEpochMillis;
            this.deadlineEpochMillis = deadlineEpochMillis;
            this.limiter = limiter;
        }

        public String sessionId() {
            return sessionId;
        }

        public String tenantId() {
            return tenantId;
        }

        public SessionState state() {
            return state;
        }

        public long createdEpochMillis() {
            return createdEpochMillis;
        }

        public int totalChunks() {
            return (int) ((declaredSize + chunkSize - 1) / chunkSize);
        }

        public int expectedChunkLength(int index) {
            long start = (long) index * chunkSize;
            return (int) Math.min(chunkSize, declaredSize - start);
        }

        public synchronized ChunkAck accept(int index, byte[] wire, TransferPolicy.ChunkEncoding encoding,
                                            CasDigest chunkDigest) {
            long now = clock.getAsLong();
            if (state != SessionState.OPEN) {
                return new ChunkAck(index, ChunkStatus.REJECTED_SESSION_CLOSED, resumeOffset(), 0,
                        "session is " + state);
            }
            if (now > deadlineEpochMillis) {
                state = SessionState.EXPIRED;
                return new ChunkAck(index, ChunkStatus.REJECTED_EXPIRED, resumeOffset(), 0,
                        "session deadline passed at " + deadlineEpochMillis);
            }
            if (index < 0 || index >= totalChunks()) {
                return new ChunkAck(index, ChunkStatus.REJECTED_RANGE, resumeOffset(), 0,
                        "chunk index outside 0.." + (totalChunks() - 1));
            }
            int expectedLength = expectedChunkLength(index);
            byte[] plain;
            try {
                plain = codec.decode(encoding, wire, expectedLength);
            } catch (RuntimeException error) {
                return new ChunkAck(index, ChunkStatus.REJECTED_DIGEST_MISMATCH, resumeOffset(), 0,
                        "chunk did not decode: " + error.getMessage());
            }
            if (plain.length != expectedLength) {
                return new ChunkAck(index, ChunkStatus.REJECTED_RANGE, resumeOffset(), 0,
                        "chunk length " + plain.length + " but expected " + expectedLength);
            }
            CasDigest actual = CasDigest.of(plain);
            if (!actual.equals(chunkDigest)) {
                return new ChunkAck(index, ChunkStatus.REJECTED_DIGEST_MISMATCH, resumeOffset(), 0,
                        "chunk hashed to " + actual.compact() + " but was declared " + chunkDigest.compact());
            }
            byte[] existing = chunks.get(index);
            if (existing != null) {
                boolean identical = java.util.Arrays.equals(existing, plain);
                return new ChunkAck(index, identical ? ChunkStatus.DUPLICATE_IDENTICAL : ChunkStatus.REJECTED_CONFLICT,
                        resumeOffset(), 0,
                        identical ? "chunk already present" : "chunk index already holds different content");
            }
            long delay = limiter == null ? 0 : limiter.reserve(plain.length, now);
            chunks.put(index, plain);
            return new ChunkAck(index, ChunkStatus.ACCEPTED, resumeOffset(), delay, "stored");
        }

        /** Byte offset of the first gap: where a resuming client should restart. */
        public synchronized long resumeOffset() {
            long offset = 0;
            for (int index = 0; index < totalChunks(); index++) {
                byte[] chunk = chunks.get(index);
                if (chunk == null) {
                    return offset;
                }
                offset += chunk.length;
            }
            return offset;
        }

        public synchronized List<Integer> missingChunks() {
            List<Integer> missing = new ArrayList<>();
            for (int index = 0; index < totalChunks(); index++) {
                if (!chunks.containsKey(index)) {
                    missing.add(index);
                }
            }
            return List.copyOf(missing);
        }

        public synchronized boolean complete() {
            return chunks.size() == totalChunks();
        }

        /**
         * Assembles, recomputes, and only then admits. A mismatch quarantines the session and
         * never reaches the store (ELMOS-CAS-010).
         */
        public synchronized CompletedUpload finish() {
            if (state != SessionState.OPEN) {
                throw new IllegalStateException("session is " + state);
            }
            if (!complete()) {
                throw new IllegalStateException("missing chunks: " + missingChunks());
            }
            ByteArrayOutputStream assembled = new ByteArrayOutputStream((int) declaredSize);
            chunks.values().forEach(chunk -> assembled.write(chunk, 0, chunk.length));
            byte[] content = assembled.toByteArray();
            CasDigest actual = CasDigest.of(content);
            if (declaredDigest.isPresent() && !declaredDigest.get().equals(actual)) {
                state = SessionState.QUARANTINED;
                String quarantineId = quarantine(sessionId, tenantId, declaredDigest.get(), actual);
                throw new CasExceptions.CasQuarantinedException(quarantineId,
                        "assembled object hashed to " + actual.compact());
            }
            boolean present = store.contains(actual);
            if (!present) {
                store.put(actual, content);
            }
            state = SessionState.COMPLETED;
            chunks.clear();
            return new CompletedUpload(actual, content.length, totalChunks(), present);
        }

        public synchronized void abort(String reason) {
            state = SessionState.ABORTED;
            chunks.clear();
        }
    }

    public Map<String, SessionState> sessionStates() {
        Map<String, SessionState> states = new LinkedHashMap<>();
        sessions.forEach((id, session) -> states.put(id, session.state));
        return Collections.unmodifiableMap(states);
    }
}
