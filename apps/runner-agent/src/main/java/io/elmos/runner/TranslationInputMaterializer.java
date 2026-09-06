package io.elmos.runner;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.Map;
import java.util.zip.ZipInputStream;

/** Materializes only the exact lease-bound, server-prepared input object. */
final class TranslationInputMaterializer {
    static final long MAX_BYTES = 96L * 1024 * 1024;

    static void materialize(Path archive, Path input, Map<String, Object> payload) throws Exception {
        Map<String, Object> object = Json.object(payload, "input");
        long expectedBytes = ((Number) object.get("byteSize")).longValue();
        String expectedDigest = Json.string(object, "sha256", "");
        if (expectedBytes < 1 || expectedBytes > MAX_BYTES || !expectedDigest.matches("[0-9a-f]{64}")) {
            throw new IOException("TRANSLATION_INPUT_DIGEST_MISMATCH");
        }
        var seen = new HashSet<String>();
        var actual = new java.util.LinkedHashMap<String, Map<String, Object>>();
        long total = 0;
        // Pin the same NOFOLLOW descriptor for authentication and extraction.
        // Rehash after extraction before any workload starts: mutation is a
        // failure, and partially materialized files never become executable.
        try (var channel=java.nio.channels.FileChannel.open(archive,StandardOpenOption.READ,java.nio.file.LinkOption.NOFOLLOW_LINKS)) {
            verify(channel,expectedBytes,expectedDigest);
            channel.position(0);
            try (InputStream raw=java.nio.channels.Channels.newInputStream(channel);ZipInputStream zip=new ZipInputStream(raw)) {
            java.util.zip.ZipEntry entry;
            byte[] buffer = new byte[64 * 1024];
            while ((entry = zip.getNextEntry()) != null) {
                String name = entry.getName();
                if (entry.isDirectory() || !safePath(name) || !seen.add(name) || seen.size() > 11_002) {
                    throw new IOException("TRANSLATION_INPUT_ARCHIVE_UNSAFE");
                }
                Path target = input.resolve(name).normalize();
                if (!target.startsWith(input)) throw new IOException("TRANSLATION_INPUT_PATH_ESCAPE");
                Files.createDirectories(target.getParent());
                MessageDigest digest = MessageDigest.getInstance("SHA-256");
                long size = 0;
                try (var out = Files.newOutputStream(target, StandardOpenOption.CREATE_NEW)) {
                    int n;
                    while ((n = zip.read(buffer)) != -1) {
                        total += n; size += n;
                        if (total > MAX_BYTES || (name.equals("manifest.json") && size > 4 * 1024 * 1024)) {
                            throw new IOException("TRANSLATION_INPUT_SIZE_LIMIT");
                        }
                        digest.update(buffer, 0, n); out.write(buffer, 0, n);
                    }
                }
                actual.put(name, Map.of("sha256", HexFormat.of().formatHex(digest.digest()), "bytes", size));
            }
            channel.position(0);
            verify(channel,expectedBytes,expectedDigest);
            }
        }
        if (!seen.contains("manifest.json")) throw new IOException("TRANSLATION_INPUT_MANIFEST_MISSING");
        Map<String, Object> manifest = Json.parseObject(Files.readString(input.resolve("manifest.json")));
        for (String field : new String[]{"tenantId", "repositoryWorkspaceId", "repositoryRef", "sourceLanguage", "targetLanguage", "casesBundleId"}) {
            if (!Json.string(manifest, field, "").equals(Json.string(payload, field, "missing"))) {
                throw new IOException("TRANSLATION_INPUT_SUBJECT_MISMATCH");
            }
        }
        var declared = new HashSet<String>();
        for (Map<String, Object> file : Json.objects(manifest, "files")) {
            String name = Json.string(file, "path", "");
            Map<String, Object> inspected = actual.get(name);
            if (name.equals("manifest.json") || !declared.add(name) || inspected == null
                    || !inspected.get("sha256").equals(file.get("sha256"))
                    || !(file.get("bytes") instanceof Number bytes)
                    || ((Number) inspected.get("bytes")).longValue() != bytes.longValue()) {
                throw new IOException("TRANSLATION_INPUT_MANIFEST_MISMATCH");
            }
        }
        if (declared.size() != seen.size() - 1
                || declared.stream().noneMatch(name -> name.startsWith("source/"))
                || declared.stream().noneMatch(name -> name.startsWith("cases/"))) {
            throw new IOException("TRANSLATION_INPUT_MANIFEST_INCOMPLETE");
        }
    }

    private static void verify(java.nio.channels.FileChannel channel,long expectedBytes,String expectedDigest) throws Exception {
        var hash=MessageDigest.getInstance("SHA-256");var buffer=java.nio.ByteBuffer.allocate(64*1024);long count=0;
        int read;
        while((read=channel.read(buffer))!=-1) {
            count+=read;if(count>expectedBytes)throw new IOException("TRANSLATION_INPUT_DIGEST_MISMATCH");
            buffer.flip();hash.update(buffer);buffer.clear();
        }
        if(count!=expectedBytes || channel.size()!=expectedBytes || !HexFormat.of().formatHex(hash.digest()).equals(expectedDigest))
            throw new IOException("TRANSLATION_INPUT_DIGEST_MISMATCH");
    }

    private static boolean safePath(String name) {
        if (name.equals("manifest.json")) return true;
        if (name.length() > 1024 || !(name.startsWith("source/") || name.startsWith("cases/"))
                || name.indexOf('\\') >= 0 || name.chars().anyMatch(c -> c < 32 || c == 127)) return false;
        for (String part : name.split("/", -1)) if (part.isEmpty() || part.equals(".") || part.equals("..")) return false;
        return true;
    }
}
