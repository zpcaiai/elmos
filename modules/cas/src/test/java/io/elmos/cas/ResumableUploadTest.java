package io.elmos.cas;

import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicLong;

import static org.junit.jupiter.api.Assertions.*;

class ResumableUploadTest {

    private final AtomicLong clock = new AtomicLong(10_000);
    private final InMemoryCasStore store = new InMemoryCasStore("l2");
    private final ResumableUploadService service = new ResumableUploadService(store, clock::get);

    private static byte[] payload(int size) {
        byte[] content = new byte[size];
        for (int index = 0; index < size; index++) {
            content[index] = (byte) ('a' + index % 26);
        }
        return content;
    }

    private static byte[] slice(byte[] content, int index, int chunkSize) {
        int from = index * chunkSize;
        return Arrays.copyOfRange(content, from, Math.min(content.length, from + chunkSize));
    }

    @Test void directUploadVerifiesAndDeduplicates() {
        byte[] content = "small blob".getBytes(StandardCharsets.UTF_8);
        CasDigest digest = CasDigest.of(content);
        var first = service.uploadDirect("tenant-a", digest, content);
        assertFalse(first.alreadyPresent());
        var second = service.uploadDirect("tenant-a", digest, content);
        assertTrue(second.alreadyPresent());
        assertEquals(1, store.inventory().size());
    }

    @Test void directUploadWithAWrongDigestIsQuarantinedNotStored() {
        byte[] content = "actual content".getBytes(StandardCharsets.UTF_8);
        CasDigest declared = CasDigest.of("something else".getBytes(StandardCharsets.UTF_8));
        assertThrows(CasExceptions.CasQuarantinedException.class,
                () -> service.uploadDirect("tenant-a", declared, content));
        assertTrue(store.inventory().isEmpty());
        assertEquals(1, service.quarantined().size());
    }

    @Test void chunkedUploadResumesFromTheFirstGap() {
        byte[] content = payload(2500);
        CasDigest digest = CasDigest.of(content);
        var session = service.open("s1", "tenant-a", content.length, 1000, Optional.of(digest), 60_000, null);
        assertEquals(3, session.totalChunks());

        session.accept(0, slice(content, 0, 1000), TransferPolicy.ChunkEncoding.NONE,
                CasDigest.of(slice(content, 0, 1000)));
        session.accept(2, slice(content, 2, 1000), TransferPolicy.ChunkEncoding.NONE,
                CasDigest.of(slice(content, 2, 1000)));

        assertEquals(1000, session.resumeOffset());
        assertEquals(List.of(1), session.missingChunks());

        session.accept(1, slice(content, 1, 1000), TransferPolicy.ChunkEncoding.NONE,
                CasDigest.of(slice(content, 1, 1000)));
        assertEquals(2500, session.resumeOffset());

        var completed = session.finish();
        assertEquals(digest, completed.digest());
        assertArrayEquals(content, store.get(digest));
    }

    @Test void aChunkThatDoesNotMatchItsDigestIsRejectedWithoutAdvancing() {
        byte[] content = payload(2000);
        var session = service.open("s2", "tenant-a", content.length, 1000, Optional.of(CasDigest.of(content)),
                60_000, null);
        byte[] good = slice(content, 0, 1000);
        byte[] tampered = good.clone();
        tampered[10] ^= 0xff;

        var ack = session.accept(0, tampered, TransferPolicy.ChunkEncoding.NONE, CasDigest.of(good));
        assertEquals(ResumableUploadService.ChunkStatus.REJECTED_DIGEST_MISMATCH, ack.status());
        assertEquals(0, session.resumeOffset());
        assertEquals(List.of(0, 1), session.missingChunks());
    }

    @Test void resendingAnIdenticalChunkIsAnAckAndResendingADifferentOneIsAConflict() {
        byte[] content = payload(1500);
        var session = service.open("s3", "tenant-a", content.length, 1000, Optional.of(CasDigest.of(content)),
                60_000, null);
        byte[] chunk = slice(content, 0, 1000);
        assertEquals(ResumableUploadService.ChunkStatus.ACCEPTED,
                session.accept(0, chunk, TransferPolicy.ChunkEncoding.NONE, CasDigest.of(chunk)).status());
        assertEquals(ResumableUploadService.ChunkStatus.DUPLICATE_IDENTICAL,
                session.accept(0, chunk, TransferPolicy.ChunkEncoding.NONE, CasDigest.of(chunk)).status());

        byte[] different = chunk.clone();
        different[0] ^= 0xff;
        assertEquals(ResumableUploadService.ChunkStatus.REJECTED_CONFLICT,
                session.accept(0, different, TransferPolicy.ChunkEncoding.NONE, CasDigest.of(different)).status());
    }

    @Test void chunksOutsideTheDeclaredRangeAreRefused() {
        byte[] content = payload(1200);
        var session = service.open("s4", "tenant-a", content.length, 1000, Optional.empty(), 60_000, null);
        byte[] chunk = slice(content, 0, 1000);
        assertEquals(ResumableUploadService.ChunkStatus.REJECTED_RANGE,
                session.accept(5, chunk, TransferPolicy.ChunkEncoding.NONE, CasDigest.of(chunk)).status());
        assertEquals(ResumableUploadService.ChunkStatus.REJECTED_RANGE,
                session.accept(1, chunk, TransferPolicy.ChunkEncoding.NONE, CasDigest.of(chunk)).status());
    }

    @Test void anAssembledObjectThatContradictsItsDeclaredDigestNeverReachesTheStore() {
        byte[] content = payload(2000);
        CasDigest wrongDeclared = new CasDigest("sha256",
                CasDigest.of("other".getBytes(StandardCharsets.UTF_8)).hex(), content.length);
        var session = service.open("s5", "tenant-a", content.length, 1000, Optional.of(wrongDeclared), 60_000, null);
        for (int index = 0; index < 2; index++) {
            byte[] chunk = slice(content, index, 1000);
            session.accept(index, chunk, TransferPolicy.ChunkEncoding.NONE, CasDigest.of(chunk));
        }
        assertThrows(CasExceptions.CasQuarantinedException.class, session::finish);
        assertTrue(store.inventory().isEmpty());
        assertEquals(ResumableUploadService.SessionState.QUARANTINED, session.state());
        assertEquals(1, service.quarantined().size());
    }

    @Test void deflatedChunksRoundTripAndCompressedMediaIsLeftAlone() {
        var policy = TransferPolicy.CompressionPolicy.standard();
        assertEquals(TransferPolicy.ChunkEncoding.DEFLATE,
                policy.encodingFor("text/x-java", "Main.java", 8192));
        assertEquals(TransferPolicy.ChunkEncoding.NONE,
                policy.encodingFor("application/java-archive", "app.jar", 8192));
        assertEquals(TransferPolicy.ChunkEncoding.NONE,
                policy.encodingFor("application/octet-stream", "sprite.png", 8192));
        assertEquals(TransferPolicy.ChunkEncoding.NONE,
                policy.encodingFor("text/plain", "tiny.txt", 10));

        byte[] content = payload(4000);
        var codec = new TransferPolicy.ChunkCodec();
        byte[] wire = codec.encode(TransferPolicy.ChunkEncoding.DEFLATE, content);
        assertTrue(wire.length < content.length);

        var session = service.open("s6", "tenant-a", content.length, 4000, Optional.of(CasDigest.of(content)),
                60_000, null);
        var ack = session.accept(0, wire, TransferPolicy.ChunkEncoding.DEFLATE, CasDigest.of(content));
        assertEquals(ResumableUploadService.ChunkStatus.ACCEPTED, ack.status());
        assertEquals(CasDigest.of(content), session.finish().digest());
    }

    @Test void bandwidthLimiterReportsTheDelayItWants() {
        var limiter = new TransferPolicy.BandwidthLimiter(1_000, 1_000, 0);
        assertEquals(0, limiter.reserve(1_000, 0));
        assertEquals(1_000, limiter.reserve(1_000, 0));
        assertEquals(0, limiter.reserve(500, 2_000));
    }

    @Test void expiredSessionsAreReportedAsIncompleteForReconciliation() {
        byte[] content = payload(2000);
        var session = service.open("s7", "tenant-a", content.length, 1000, Optional.of(CasDigest.of(content)),
                1_000, null);
        byte[] chunk = slice(content, 0, 1000);
        session.accept(0, chunk, TransferPolicy.ChunkEncoding.NONE, CasDigest.of(chunk));

        clock.addAndGet(5_000);
        var incomplete = service.incompleteSessions();
        assertEquals(1, incomplete.size());
        assertEquals("s7", incomplete.get(0).sessionId());
        assertEquals(ResumableUploadService.SessionState.EXPIRED, incomplete.get(0).state());

        var ack = session.accept(1, slice(content, 1, 1000), TransferPolicy.ChunkEncoding.NONE,
                CasDigest.of(slice(content, 1, 1000)));
        assertEquals(ResumableUploadService.ChunkStatus.REJECTED_SESSION_CLOSED, ack.status());
    }
}
