package io.elmos.cas;

import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.*;

class CasManifestAndSecurityTest {

    private static CasDigest digest(String text) {
        return CasDigest.of(text.getBytes(StandardCharsets.UTF_8));
    }

    private static MerkleTree.CanonicalTree tree() {
        return MerkleTree.canonicalize(List.of(
                new MerkleTree.FileNode("a.txt", digest("a"), false),
                new MerkleTree.FileNode("b.txt", digest("b"), false)), List.of());
    }

    @Test void manifestDigestIsStableAcrossBlobOrderAndAttributeOrder() {
        var canonical = tree();
        CasManifest first = new CasManifest(CasManifest.SCHEMA_VERSION, CasManifest.Kind.OUTPUT, "tenant-a",
                "project-a", canonical.rootDigest(), List.of(digest("a"), digest("b")),
                Map.of("z", "1", "a", "2"), Optional.empty());
        CasManifest second = new CasManifest(CasManifest.SCHEMA_VERSION, CasManifest.Kind.OUTPUT, "tenant-a",
                "project-a", canonical.rootDigest(), List.of(digest("b"), digest("a")),
                Map.of("a", "2", "z", "1"), Optional.empty());
        assertEquals(first.digest(), second.digest());
    }

    @Test void inputAndOutputManifestsAreNeverInterchangeable() {
        var canonical = tree();
        CasManifest input = new CasManifest(CasManifest.SCHEMA_VERSION, CasManifest.Kind.INPUT_ROOT, "tenant-a",
                "project-a", canonical.rootDigest(), List.of(), Map.of(), Optional.empty());
        CasManifest output = new CasManifest(CasManifest.SCHEMA_VERSION, CasManifest.Kind.OUTPUT, "tenant-a",
                "project-a", canonical.rootDigest(), List.of(), Map.of(), Optional.empty());
        assertNotEquals(input.digest(), output.digest());
    }

    @Test void manifestsOfDifferentTenantsNeverCollide() {
        var canonical = tree();
        CasManifest a = new CasManifest(CasManifest.SCHEMA_VERSION, CasManifest.Kind.OUTPUT, "tenant-a",
                "project-a", canonical.rootDigest(), List.of(), Map.of(), Optional.empty());
        CasManifest b = new CasManifest(CasManifest.SCHEMA_VERSION, CasManifest.Kind.OUTPUT, "tenant-b",
                "project-a", canonical.rootDigest(), List.of(), Map.of(), Optional.empty());
        assertNotEquals(a.digest(), b.digest());
    }

    @Test void duplicateBlobReferencesAreRefused() {
        var canonical = tree();
        assertThrows(IllegalArgumentException.class, () -> new CasManifest(CasManifest.SCHEMA_VERSION,
                CasManifest.Kind.OUTPUT, "tenant-a", "project-a", canonical.rootDigest(),
                List.of(digest("a"), digest("a")), Map.of(), Optional.empty()));
    }

    @Test void manifestJsonCarriesTheSchemaShape() {
        CasManifest manifest = CasManifest.output("tenant-a", "project-a", tree(), List.of(digest("a")));
        String json = manifest.toJson();
        assertTrue(json.contains("\"schema_version\":\"1.0\""));
        assertTrue(json.contains("\"algorithm\":\"sha256\""));
        assertTrue(json.contains("\"size_bytes\":"));
        assertTrue(json.contains("\"file_count\""));
    }

    @Test void tenantEncryptionUsesFreshNoncesAndRefusesForeignTenants() {
        var encryption = new TenantEncryption.AesGcm()
                .registerKey("tenant-a", new byte[32])
                .registerKey("tenant-b", new byte[32]);
        byte[] content = "shared plaintext".getBytes(StandardCharsets.UTF_8);
        CasDigest contentDigest = CasDigest.of(content);

        byte[] first = encryption.encrypt("tenant-a", contentDigest, content);
        byte[] second = encryption.encrypt("tenant-a", contentDigest, content);
        assertFalse(java.util.Arrays.equals(first, second),
                "fresh GCM nonces must not repeat ciphertext for a re-upload");
        assertArrayEquals(content, encryption.decrypt("tenant-a", contentDigest, first));

        // Same key material, different tenant: the tenant id is authenticated data, so the tag fails.
        assertThrows(CasExceptions.CasAccessDeniedException.class,
                () -> encryption.decrypt("tenant-b", contentDigest, first));
        assertThrows(CasExceptions.CasAccessDeniedException.class,
                () -> encryption.encrypt("tenant-c", contentDigest, content));
    }

    @Test void tamperedCiphertextIsRejected() {
        var encryption = new TenantEncryption.AesGcm().registerKey("tenant-a", new byte[32]);
        byte[] content = "authentic".getBytes(StandardCharsets.UTF_8);
        CasDigest contentDigest = CasDigest.of(content);
        byte[] ciphertext = encryption.encrypt("tenant-a", contentDigest, content);
        ciphertext[0] ^= 0xff;
        assertThrows(CasExceptions.CasAccessDeniedException.class,
                () -> encryption.decrypt("tenant-a", contentDigest, ciphertext));
    }

    @Test void tenantKeyIdsAreImmutableButIdempotentRegistrationIsAllowed() {
        byte[] original = new byte[32];
        byte[] replacement = new byte[32];
        java.util.Arrays.fill(replacement, (byte) 1);
        var encryption = new TenantEncryption.AesGcm()
                .registerKey("tenant-a", "v1", original, true)
                .registerKey("tenant-a", "v1", original, true);

        assertTrue(encryption.hasKey("tenant-a"));
        assertThrows(IllegalArgumentException.class,
                () -> encryption.registerKey("tenant-a", "v1", replacement, true));
    }

    @Test void encryptionRefusesPlaintextThatDoesNotMatchItsDeclaredDigest() {
        var encryption = new TenantEncryption.AesGcm().registerKey("tenant-a", new byte[32]);
        byte[] plaintext = "actual".getBytes(StandardCharsets.UTF_8);

        assertThrows(CasExceptions.CasCorruptionException.class,
                () -> encryption.seal("tenant-a", digest("different"), plaintext));
        assertThrows(CasExceptions.CasCorruptionException.class,
                () -> encryption.encrypt("tenant-a", digest("different"), plaintext));
    }

    @Test void secretsAreRemovedFromCachedLogsAndReplacedByAStableFingerprint() {
        var redaction = new LogRedaction()
                .withSecret("ghp_supersecrettoken")
                .withSecret("ab");
        var redacted = redaction.redact("using token ghp_supersecrettoken to push; ab stays");
        String text = new String(redacted.content(), StandardCharsets.UTF_8);

        assertFalse(text.contains("ghp_supersecrettoken"));
        assertTrue(text.contains("[REDACTED:" + LogRedaction.fingerprint("ghp_supersecrettoken") + "]"));
        assertTrue(text.contains("ab stays"), "values below the minimum length must not be redacted");
        assertEquals(CasDigest.of(redacted.content()), redacted.digest());
        assertEquals(1, redacted.redactedFingerprints().size());
    }

    @Test void resultRecordsRefuseSelfContradictoryStates() {
        CasDigest manifest = digest("manifest");
        var usage = new ActionResultRecord.ResourceUsage(1, 1, 0, 0, 0, 1);
        assertThrows(IllegalArgumentException.class, () -> new ActionResultRecord(
                ActionResultRecord.SCHEMA_VERSION, "act-1", 1, 1, "receipt-1",
                ActionResultRecord.Status.SUCCEEDED, "s", "f", 3, manifest, Optional.empty(), Optional.empty(),
                usage, Map.of(), Optional.empty(), Optional.empty(), ActionResultRecord.ValidationStatus.PASS,
                manifest));
        assertThrows(IllegalArgumentException.class, () -> new ActionResultRecord(
                ActionResultRecord.SCHEMA_VERSION, "act-1", 1, 1, "receipt-1",
                ActionResultRecord.Status.FAILED, "s", "f", 1, manifest, Optional.empty(), Optional.empty(),
                usage, Map.of(), Optional.empty(), Optional.empty(), ActionResultRecord.ValidationStatus.FAIL,
                manifest));
        assertFalse(ActionResultRecord.failed("act-1", "receipt-1", 1,
                ActionResultRecord.FailureClass.ENVIRONMENT, "disk full", manifest, manifest, usage, "s", "f")
                .reusable());
        assertTrue(ActionResultRecord.failed("act-1", "receipt-1", 1,
                ActionResultRecord.FailureClass.CODE, "does not compile", manifest, manifest, usage, "s", "f")
                .reusable());
    }

    @Test void resultRecordsRefuseNonFiniteUsageAndCost() {
        assertThrows(IllegalArgumentException.class,
                () -> new ActionResultRecord.ResourceUsage(
                        Double.NaN, 1, 0, 0, 0, 1));
        assertThrows(IllegalArgumentException.class,
                () -> new ActionResultRecord.ResourceUsage(
                        1, Double.POSITIVE_INFINITY, 0, 0, 0, 1));

        CasDigest manifest = digest("finite-result");
        var usage = new ActionResultRecord.ResourceUsage(1, 1, 0, 0, 0, 1);
        assertThrows(IllegalArgumentException.class, () -> new ActionResultRecord(
                ActionResultRecord.SCHEMA_VERSION, "act-1", 1, 1, "receipt-1",
                ActionResultRecord.Status.SUCCEEDED, "s", "f", 0, manifest,
                Optional.empty(), Optional.empty(), usage,
                Map.of("usd", Double.NEGATIVE_INFINITY), Optional.empty(), Optional.empty(),
                ActionResultRecord.ValidationStatus.PASS, manifest));
    }
}
