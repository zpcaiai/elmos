package io.elmos.runner;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.DigestInputStream;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.List;
import java.util.Locale;

/**
 * Uploads workload outputs straight to object storage.
 *
 * <p>The control plane is not in the data path. It issues a presigned PUT and,
 * afterwards, recomputes the digest server-side before the artifact becomes
 * downloadable. This agent's declared digest is therefore a claim to be checked,
 * never a fact to be trusted - which is what makes a truncated upload impossible
 * to publish as a good archive.</p>
 */
public final class ArtifactPublisher {

    /** Above this, the upload is refused rather than attempted and timed out. */
    private static final long MAX_ARTIFACT_BYTES = 5L * 1024 * 1024 * 1024;

    private final ControlPlaneClient client;
    private final AgentMetrics metrics;

    public ArtifactPublisher(ControlPlaneClient client, AgentMetrics metrics) {
        this.client = client;
        this.metrics = metrics;
    }

    public record Published(String filename, String role, String sha256, long byteSize) {
    }

    public List<Published> publishAll(ControlPlaneClient.Lease lease, JobWorkspace workspace) throws IOException {
        List<Path> outputs = workspace.outputs();
        List<Published> published = new java.util.ArrayList<>();
        for (Path file : outputs) {
            published.add(publish(lease, workspace, file));
        }
        return published;
    }

    Published publish(ControlPlaneClient.Lease lease, JobWorkspace workspace, Path file) throws IOException {
        long size = Files.size(file);
        if (size == 0) {
            throw new IOException("ARTIFACT_EMPTY");
        }
        if (size > MAX_ARTIFACT_BYTES) {
            throw new IOException("ARTIFACT_TOO_LARGE");
        }

        String relative = workspace.out().relativize(file).toString();
        String role = roleFor(relative);
        String mediaType = mediaTypeFor(relative);
        String sha256 = sha256(file);

        ControlPlaneClient.UploadTicket ticket = client.requestUploadTicket(lease, sha256, size, mediaType);
        client.uploadArtifact(ticket, file, mediaType);
        client.publishArtifact(lease, ticket.contentObjectId(), role, relative);

        metrics.increment(AgentMetrics.ARTIFACTS_PUBLISHED);
        return new Published(relative, role, sha256, size);
    }

    /** Streaming digest: a multi-gigabyte archive must never be held in memory. */
    static String sha256(Path file) throws IOException {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            try (InputStream in = Files.newInputStream(file);
                 DigestInputStream digesting = new DigestInputStream(in, digest)) {
                byte[] buffer = new byte[1 << 16];
                while (digesting.read(buffer) != -1) {
                    // Reading is the point; the digest updates as a side effect.
                }
            }
            return HexFormat.of().formatHex(digest.digest()).toLowerCase(Locale.ROOT);
        } catch (java.security.NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }

    /**
     * Maps a produced file to one of the roles the schema accepts. The workload
     * declares its intent through a fixed directory convention rather than through
     * a manifest it could forge.
     */
    static String roleFor(String relativePath) {
        String path = relativePath.replace('\\', '/').toLowerCase(Locale.ROOT);
        if (path.startsWith("evidence/")) {
            return "EVIDENCE_PACK";
        }
        if (path.startsWith("logs/") || path.endsWith(".log")) {
            return "BUILD_LOG";
        }
        if (path.startsWith("reports/") || path.contains("test-report")) {
            return "TEST_REPORT";
        }
        if (path.endsWith(".spdx.json") || path.endsWith(".cdx.json") || path.contains("sbom")) {
            return "SBOM";
        }
        if (path.endsWith(".patch") || path.endsWith(".diff")) {
            return "DIFF";
        }
        if (path.equals("pull-request.md")) {
            return "PULL_REQUEST_BODY";
        }
        if (path.startsWith("gate/") || path.contains("gate-report")) {
            return "GATE_REPORT";
        }
        return "PROJECT_ARCHIVE";
    }

    static String mediaTypeFor(String relativePath) {
        String path = relativePath.toLowerCase(Locale.ROOT);
        if (path.endsWith(".zip")) {
            return "application/zip";
        }
        if (path.endsWith(".tar.zst")) {
            return "application/zstd";
        }
        if (path.endsWith(".json")) {
            return "application/json";
        }
        if (path.endsWith(".md") || path.endsWith(".log") || path.endsWith(".txt")
                || path.endsWith(".patch") || path.endsWith(".diff")) {
            return "text/plain; charset=utf-8";
        }
        return "application/octet-stream";
    }
}
