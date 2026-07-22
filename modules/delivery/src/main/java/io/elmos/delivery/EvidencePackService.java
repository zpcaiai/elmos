package io.elmos.delivery;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.github.luben.zstd.ZstdInputStream;
import com.github.luben.zstd.ZstdOutputStream;
import io.elmos.delivery.DeliveryModels.*;
import org.apache.commons.compress.archivers.tar.TarArchiveEntry;
import org.apache.commons.compress.archivers.tar.TarArchiveInputStream;
import org.apache.commons.compress.archivers.tar.TarArchiveOutputStream;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.util.*;

public final class EvidencePackService {
    private static final Set<String> ALLOWED_PREFIXES = Set.of("metadata/", "evidence/", "reports/", "rollback/", "scm/", "manifests/");
    private final ObjectMapper json;
    public EvidencePackService(ObjectMapper json) { this.json = Objects.requireNonNull(json); }

    public EvidencePack create(List<EvidenceEntry> input, PrivateKey signingKey, PublicKey publicKey) {
        List<EvidenceEntry> entries = input.stream().sorted(Comparator.comparing(EvidenceEntry::path)).toList();
        validate(entries);
        List<EvidenceManifestEntry> manifestEntries = entries.stream().map(entry -> new EvidenceManifestEntry(
                entry.path(), DeliveryReadModel.hash(entry.content()), entry.content().length, entry.mediaType())).toList();
        Map<String,Object> manifestObject = new TreeMap<>();
        manifestObject.put("schemaVersion", "1.0"); manifestObject.put("algorithm", "SHA-256");
        manifestObject.put("signatureAlgorithm", "Ed25519"); manifestObject.put("entries", manifestEntries);
        byte[] manifest = write(manifestObject); byte[] signature = sign(manifest, signingKey); byte[] encodedPublicKey = publicKey.getEncoded();
        String packId = "evidence-pack-" + DeliveryReadModel.hash(manifest).substring(0, 24);
        List<EvidenceEntry> archiveEntries = new ArrayList<>(entries);
        archiveEntries.add(new EvidenceEntry("manifests/evidence-manifest.json", manifest, "application/json", false));
        archiveEntries.add(new EvidenceEntry("manifests/evidence-manifest.ed25519", signature, "application/octet-stream", false));
        archiveEntries.add(new EvidenceEntry("manifests/evidence-public-key.der", encodedPublicKey, "application/pkix-cert", false));
        byte[] archive = tarZstd(archiveEntries.stream().sorted(Comparator.comparing(EvidenceEntry::path)).toList());
        return new EvidencePack(packId, archive, manifest, signature, encodedPublicKey, DeliveryReadModel.hash(archive), manifestEntries);
    }

    public boolean verify(EvidencePack pack, PublicKey trustedPublicKey) {
        try {
            if (!DeliveryReadModel.hash(pack.archive()).equals(pack.archiveSha256())) return false;
            Signature verifier = Signature.getInstance("Ed25519"); verifier.initVerify(trustedPublicKey); verifier.update(pack.manifest());
            if (!verifier.verify(pack.signature())) return false;
            Map<String,byte[]> contents = readTarZstd(pack.archive());
            if (!Arrays.equals(contents.get("manifests/evidence-manifest.json"), pack.manifest())
                    || !Arrays.equals(contents.get("manifests/evidence-manifest.ed25519"), pack.signature())
                    || !Arrays.equals(contents.get("manifests/evidence-public-key.der"), pack.publicKey())) return false;
            for (EvidenceManifestEntry entry : pack.entries()) {
                byte[] content = contents.get(entry.path());
                if (content == null || content.length != entry.size() || !DeliveryReadModel.hash(content).equals(entry.sha256())) return false;
            }
            return true;
        } catch (Exception error) { return false; }
    }

    private void validate(List<EvidenceEntry> entries) {
        Set<String> paths = new HashSet<>();
        for (EvidenceEntry entry : entries) {
            String path = entry.path(); String lower = path.toLowerCase(Locale.ROOT);
            if (path.startsWith("/") || path.contains("..") || !ALLOWED_PREFIXES.stream().anyMatch(path::startsWith))
                throw new SecurityException("evidence entry path is outside package policy: " + path);
            if (!paths.add(path)) throw new IllegalArgumentException("duplicate evidence entry: " + path);
            if (entry.sensitive() || lower.contains("secret") || lower.contains("token") || lower.contains("credential")
                    || lower.contains("private-key") || lower.endsWith(".env") || lower.startsWith("evidence/source/")
                    || lower.contains("full-source"))
                throw new SecurityException("sensitive or full-source evidence is forbidden: " + path);
        }
    }

    private byte[] write(Object value) {
        try { return json.writer().with(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS).writeValueAsBytes(value); }
        catch (Exception error) { throw new IllegalStateException("evidence manifest serialization failed", error); }
    }

    private static byte[] sign(byte[] manifest, PrivateKey key) {
        try { Signature signature = Signature.getInstance("Ed25519"); signature.initSign(key); signature.update(manifest); return signature.sign(); }
        catch (Exception error) { throw new IllegalStateException("evidence manifest signing failed", error); }
    }

    private static byte[] tarZstd(List<EvidenceEntry> entries) {
        try {
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            try (ZstdOutputStream zstd = new ZstdOutputStream(bytes); TarArchiveOutputStream tar = new TarArchiveOutputStream(zstd)) {
                tar.setLongFileMode(TarArchiveOutputStream.LONGFILE_POSIX);
                for (EvidenceEntry value : entries) {
                    byte[] content = value.content(); TarArchiveEntry entry = new TarArchiveEntry(value.path());
                    entry.setSize(content.length); entry.setModTime(0); entry.setUserId(0); entry.setGroupId(0);
                    entry.setUserName(""); entry.setGroupName(""); entry.setMode(0644);
                    tar.putArchiveEntry(entry); tar.write(content); tar.closeArchiveEntry();
                }
                tar.finish();
            }
            return bytes.toByteArray();
        } catch (Exception error) { throw new IllegalStateException("evidence archive creation failed", error); }
    }

    private static Map<String,byte[]> readTarZstd(byte[] archive) throws Exception {
        Map<String,byte[]> result = new HashMap<>();
        try (ZstdInputStream zstd = new ZstdInputStream(new ByteArrayInputStream(archive));
             TarArchiveInputStream tar = new TarArchiveInputStream(zstd)) {
            TarArchiveEntry entry;
            while ((entry = tar.getNextEntry()) != null) {
                if (entry.isDirectory() || entry.getName().startsWith("/") || entry.getName().contains("..")) return Map.of();
                result.put(entry.getName(), tar.readAllBytes());
            }
        }
        return result;
    }
}
