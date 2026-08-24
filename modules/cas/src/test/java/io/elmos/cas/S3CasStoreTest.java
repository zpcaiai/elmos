package io.elmos.cas;

import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.net.http.HttpClient;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

class S3CasStoreTest {

    private static final String ACCESS_KEY = "AKIAELMOSTESTKEY";
    private static final String SECRET_KEY = "elmos/test/secret/key/0123456789";

    private static byte[] bytes(String text) {
        return text.getBytes(StandardCharsets.UTF_8);
    }

    private static byte[] payload(int size) {
        byte[] content = new byte[size];
        for (int index = 0; index < size; index++) {
            content[index] = (byte) (index % 251);
        }
        return content;
    }

    private record Fixture(MockS3Server server, S3CasStore store) implements AutoCloseable {
        @Override
        public void close() {
            server.close();
        }
    }

    private static Fixture fixture(long multipartThreshold, long partSize) throws IOException {
        MockS3Server server = new MockS3Server("elmos-cas", ACCESS_KEY, SECRET_KEY, "eu-west-1");
        var config = new S3CasStore.Config(server.endpoint(), "elmos-cas", "eu-west-1", "cas",
                ACCESS_KEY, SECRET_KEY, Optional.empty(), true, multipartThreshold, partSize, 3,
                Duration.ofSeconds(10));
        return new Fixture(server, new S3CasStore("l2-s3", config,
                HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build(), Instant::now));
    }

    private static Fixture fixture() throws IOException {
        return fixture(1024 * 1024, 1024 * 1024);
    }

    @Test void putAndGetRoundTripThroughASignedRequest() throws Exception {
        try (Fixture fixture = fixture()) {
            byte[] content = bytes("hello from the shared tier");
            CasDigest digest = CasDigest.of(content);

            fixture.store().put(digest, content);
            assertEquals(0, fixture.server().signatureRejections(), "every request must be correctly signed");
            assertTrue(fixture.store().contains(digest));
            assertArrayEquals(content, fixture.store().get(digest));
            assertTrue(fixture.server().objects().containsKey("cas/" + digest.shardPath()));
        }
    }

    @Test void aWrongSecretIsRejectedByTheEndpointRatherThanSilentlyAccepted() throws Exception {
        try (MockS3Server server = new MockS3Server("elmos-cas", ACCESS_KEY, SECRET_KEY, "eu-west-1")) {
            var config = new S3CasStore.Config(server.endpoint(), "elmos-cas", "eu-west-1", "cas",
                    ACCESS_KEY, "the-wrong-secret-key-000000000000", Optional.empty(), true,
                    1024 * 1024, 1024 * 1024, 1, Duration.ofSeconds(10));
            var store = new S3CasStore("l2-s3", config, HttpClient.newHttpClient(), Instant::now);

            var error = assertThrows(CasExceptions.CasAccessDeniedException.class,
                    () -> store.contains(CasDigest.of(bytes("x"))));
            assertEquals("OBJECT_STORE_REJECTED_CREDENTIALS", error.reason());
            assertEquals(1, server.signatureRejections());
        }
    }

    @Test void storingContentUnderAForeignDigestNeverReachesTheNetwork() throws Exception {
        try (Fixture fixture = fixture()) {
            CasDigest lie = CasDigest.of(bytes("expected"));
            assertThrows(CasExceptions.CasCorruptionException.class, () -> fixture.store().put(lie, bytes("actual")));
            assertEquals(0, fixture.server().requestCount());
        }
    }

    @Test void anObjectCorruptedByTheStoreIsDetectedOnDownload() throws Exception {
        try (Fixture fixture = fixture()) {
            byte[] content = bytes("trusted artifact");
            CasDigest digest = CasDigest.of(content);
            fixture.store().put(digest, content);
            fixture.server().corruptOnGet("cas/" + digest.shardPath());

            assertThrows(CasExceptions.CasCorruptionException.class, () -> fixture.store().get(digest));
        }
    }

    @Test void aKeyWithTheWrongLengthIsNotACacheHit() throws Exception {
        try (Fixture fixture = fixture()) {
            CasDigest digest = CasDigest.of(payload(4096));
            // An aborted multipart upload can leave a short object under the right key.
            fixture.server().putDirectly("cas/" + digest.shardPath(), payload(100));
            assertFalse(fixture.store().contains(digest));
        }
    }

    @Test void missingObjectsAreReportedRatherThanThrown() throws Exception {
        try (Fixture fixture = fixture()) {
            CasDigest absent = CasDigest.of(bytes("absent"));
            assertFalse(fixture.store().contains(absent));
            assertThrows(CasExceptions.CasNotFoundException.class, () -> fixture.store().get(absent));
            assertEquals(Set.of(absent), fixture.store().missing(List.of(absent)));
        }
    }

    @Test void rangeReadsAreServedByTheEndpointAndBoundedByTheObjectSize() throws Exception {
        try (Fixture fixture = fixture()) {
            byte[] content = bytes("abcdefghij");
            CasDigest digest = CasDigest.of(content);
            fixture.store().put(digest, content);

            assertArrayEquals(bytes("cde"), fixture.store().readRange(digest, 2, 3));
            assertArrayEquals(bytes("ij"), fixture.store().readRange(digest, 8, 100));
            assertEquals(0, fixture.store().readRange(digest, 10, 5).length);
            assertThrows(IllegalArgumentException.class, () -> fixture.store().readRange(digest, 11, 1));
        }
    }

    @Test void largeObjectsGoThroughMultipartUploadAndReassembleExactly() throws Exception {
        try (Fixture fixture = fixture(4096, 1024)) {
            byte[] content = payload(10_000);
            CasDigest digest = CasDigest.of(content);

            fixture.store().put(digest, content);
            assertEquals(0, fixture.server().signatureRejections());
            assertArrayEquals(content, fixture.server().objects().get("cas/" + digest.shardPath()));
            assertArrayEquals(content, fixture.store().get(digest));
        }
    }

    @Test void anAbandonedMultipartUploadIsAborted() throws Exception {
        try (Fixture fixture = fixture(4096, 1024)) {
            byte[] content = payload(10_000);
            CasDigest digest = CasDigest.of(content);
            // Fail every attempt of the first UploadPart. CreateMultipartUpload still succeeds, so
            // there is a live upload id that must be cleaned up on the way out.
            fixture.server().failNextPartUploads(3);

            assertThrows(RuntimeException.class, () -> fixture.store().put(digest, content));
            assertEquals(1, fixture.server().abortedUploads().size());
            assertFalse(fixture.server().objects().containsKey("cas/" + digest.shardPath()));
        }
    }

    @Test void transientServerErrorsAreRetriedAndThenSucceed() throws Exception {
        try (Fixture fixture = fixture()) {
            byte[] content = bytes("eventually consistent");
            CasDigest digest = CasDigest.of(content);
            fixture.server().failNextRequests(2);

            fixture.store().put(digest, content);
            assertArrayEquals(content, fixture.store().get(digest));
        }
    }

    @Test void inventoryPagesThroughContinuationTokens() throws Exception {
        try (Fixture fixture = fixture()) {
            fixture.server().maxKeysPerPage(2);
            for (int index = 0; index < 7; index++) {
                byte[] content = bytes("object-" + index);
                fixture.store().put(CasDigest.of(content), content);
            }
            fixture.server().putDirectly("cas/sha256/zz/zz/not-a-digest", bytes("stray"));

            Set<CasDigest> inventory = fixture.store().inventory();
            assertEquals(7, inventory.size(), "the stray key must be skipped, not crash the listing");
            assertTrue(inventory.contains(CasDigest.of(bytes("object-3"))));
            assertEquals(inventory.stream().mapToLong(CasDigest::sizeBytes).sum(), fixture.store().totalBytes());
        }
    }

    @Test void deleteReportsWhetherTheObjectWasThere() throws Exception {
        try (Fixture fixture = fixture()) {
            byte[] content = bytes("temporary");
            CasDigest digest = CasDigest.of(content);
            fixture.store().put(digest, content);

            assertTrue(fixture.store().delete(digest));
            assertFalse(fixture.store().contains(digest));
            assertFalse(fixture.store().delete(digest));
        }
    }

    @Test void theS3TierComposesUnderTheTieredStore() throws Exception {
        try (Fixture fixture = fixture()) {
            InMemoryCasStore local = new InMemoryCasStore("l1");
            var tiered = new TieredCasStore(local, fixture.store(), TieredCasStore.TierPolicy.unbounded(),
                    () -> 1_000L);
            byte[] content = bytes("promoted through the tiers");
            CasDigest digest = CasDigest.of(content);

            tiered.putDurable(digest, content);
            assertTrue(fixture.store().contains(digest));

            local.delete(digest);
            assertArrayEquals(content, tiered.get(digest));
            assertTrue(local.contains(digest), "read-through must repopulate the local tier");
        }
    }

    @Test void awsRejectsUndersizedPartsSoTheConfigCanBeCheckedUpFront() {
        var minio = S3CasStore.Config.minio(java.net.URI.create("http://localhost:9000"), "b", "k", "s");
        minio.validateForAws();
        var tiny = new S3CasStore.Config(java.net.URI.create("http://localhost:9000"), "b", "us-east-1", "cas",
                "k", "s", Optional.empty(), true, 1024, 1024, 3, Duration.ofSeconds(5));
        assertThrows(IllegalStateException.class, tiny::validateForAws);
    }

    @Test void canonicalisationFollowsTheSigV4RulesThatUrlEncoderGetsWrong() {
        // Shared with the presigned-URL path, so these hold for both flavours.
        assertEquals("continuation-token=2&list-type=2&prefix=cas%2Fsha256%2F",
                io.elmos.storage.SigV4Presigner.canonicalQuery(new java.util.LinkedHashMap<>(
                        java.util.Map.of("prefix", "cas/sha256/", "list-type", "2",
                                "continuation-token", "2"))));
        assertEquals("a%20b", io.elmos.storage.SigV4Presigner.canonicalQuery(
                java.util.Map.of("k", "a b")).substring(2));
    }

    @Test void aLeadingSlashSurvivesCanonicalisation() {
        // encodePath alone drops it, and a canonical URI without the leading slash signs a
        // different request than the one that goes on the wire.
        assertEquals("/elmos-cas/cas/sha256/aa/bb/cc",
                io.elmos.storage.SigV4Presigner.canonicalUri("/elmos-cas/cas/sha256/aa/bb/cc"));
        assertEquals("/", io.elmos.storage.SigV4Presigner.canonicalUri(""));
        assertEquals("/", io.elmos.storage.SigV4Presigner.canonicalUri("/"));
        assertEquals("/a%20b", io.elmos.storage.SigV4Presigner.canonicalUri("/a b"));
    }
}
