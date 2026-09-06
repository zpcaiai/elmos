package io.elmos.runner;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.util.Map;

/** Trusted launcher phase receipts, not commands parsed from customer stdout. */
final class TranslationJobProtocol {
    static final String KIND = "translate-pipeline-v1";
    static boolean applies(ControlPlaneClient.Lease lease) {
        return lease.businessLine().equals("TRANSLATION") && lease.jobKind().equals(KIND);
    }

    static Map<String, Object> readReceipt(Path file) throws IOException {
        var before=Files.readAttributes(file,java.nio.file.attribute.BasicFileAttributes.class,LinkOption.NOFOLLOW_LINKS);
        if (!before.isRegularFile() || before.size()<1 || before.size()>2*1024*1024) {
            throw new IOException("TRANSLATION_PHASE_RECEIPT_INVALID");
        }
        byte[] bytes;
        try(var channel=java.nio.channels.FileChannel.open(file,java.nio.file.StandardOpenOption.READ,LinkOption.NOFOLLOW_LINKS)) {
            if(channel.size()!=before.size())throw new IOException("TRANSLATION_PHASE_RECEIPT_CHANGED");
            bytes=readBoundedReceipt(channel,before.size());
            var after=Files.readAttributes(file,java.nio.file.attribute.BasicFileAttributes.class,LinkOption.NOFOLLOW_LINKS);
            if(!after.isRegularFile() || !java.util.Objects.equals(before.fileKey(),after.fileKey())
                    || before.size()!=after.size() || channel.size()!=before.size()
                    || !before.lastModifiedTime().equals(after.lastModifiedTime()))
                throw new IOException("TRANSLATION_PHASE_RECEIPT_CHANGED");
        }
        return Json.parseObject(java.nio.charset.StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(java.nio.charset.CodingErrorAction.REPORT)
                .decode(java.nio.ByteBuffer.wrap(bytes)).toString());
    }

    static byte[] readBoundedReceipt(java.nio.channels.ReadableByteChannel channel,long expectedSize) throws IOException {
        var buffer=java.nio.ByteBuffer.allocate(2*1024*1024+1);
        int emptyReads=0;
        while(buffer.hasRemaining()) {
            int read=channel.read(buffer);
            if(read<0)break;
            if(read==0 && ++emptyReads>32)throw new IOException("TRANSLATION_PHASE_RECEIPT_STALLED");
        }
        if(buffer.position()!=expectedSize || buffer.position()>2*1024*1024)
            throw new IOException("TRANSLATION_PHASE_RECEIPT_CHANGED");
        return java.util.Arrays.copyOf(buffer.array(),buffer.position());
    }

    static void verifyPreflight(Path file, Map<String, Object> input) throws IOException {
        var value = readReceipt(file);
        if (!Json.string(value, "kind", "").equals("elmos.repository-conversion-preflight")
                || !Json.string(value, "schema_version", "").equals("1.0.0")
                || !Json.string(value, "execution_status", "").equals("NOT_RUN")
                || !Json.string(value, "certification_status", "").equals("NOT_CERTIFIED")
                || !Json.string(value, "repository_ref", "").equals(input.get("repositoryRef"))
                || !Json.string(value, "source_language", "").equals(input.get("sourceLanguage"))
                || !Json.string(value, "target_language", "").equals(input.get("targetLanguage"))
                || !Json.string(value,"route_id","").equals(input.get("sourceLanguage")+"-to-"+input.get("targetLanguage"))
                || !Json.string(value, "snapshot_sha256", "").matches("[0-9a-f]{64}")) {
            throw new IOException("TRANSLATION_PREFLIGHT_SUBJECT_INVALID");
        }
        String status = Json.string(value, "status", "");
        if (!(status.equals("PASSED") || status.equals("PASSED_WITH_INCOMPLETE_INVENTORY"))
                || integer(value.get("obligation_count")) < 0 || integer(value.get("obligation_count")) > 10_000
                || integer(value.get("obligation_limit")) != 10_000
                || integer(value.get("reported_obligation_lower_bound")) != integer(value.get("obligation_count"))
                || value.get("reason_code") != null) {
            throw new IOException("TRANSLATION_PREFLIGHT_REJECTED");
        }
        boolean complete = Boolean.TRUE.equals(value.get("count_complete"));
        if (!(value.get("count_complete") instanceof Boolean)
                || !Json.string(value,"obligation_count_semantics","").equals(complete ? "EXACT_REPORTED_ROWS" : "REPORTED_ROW_LOWER_BOUND")
                || !Json.string(value,"actual_obligation_count_status","").equals(complete ? "EXACT" : "UNKNOWN")
                || (complete ? integer(value.get("actual_obligation_count")) != integer(value.get("obligation_count"))
                    : value.get("actual_obligation_count") != null)
                || !status.equals(complete ? "PASSED" : "PASSED_WITH_INCOMPLETE_INVENTORY")) {
            throw new IOException("TRANSLATION_PREFLIGHT_COUNT_INVALID");
        }
        var identity = new java.util.TreeMap<>(value);
        identity.remove("preflight_id");
        try {
            String digest = java.util.HexFormat.of().formatHex(java.security.MessageDigest.getInstance("SHA-256")
                    .digest(Json.write(identity).getBytes(java.nio.charset.StandardCharsets.UTF_8)));
            if (!("sha256:" + digest).equals(value.get("preflight_id"))) throw new IOException("TRANSLATION_PREFLIGHT_IDENTITY_INVALID");
        } catch (java.security.NoSuchAlgorithmException error) { throw new IOException(error); }
    }

    static String result(Path file, Map<String, Object> input) throws IOException {
        Map<String, Object> value = readReceipt(file);
        if (!Json.string(value, "schemaVersion", "").equals("translation-hosted-result-v1")
                || !Json.string(value, "inputSha256", "").equals(Json.object(input, "input").get("sha256"))
                || !Json.string(value, "repositoryRef", "").equals(input.get("repositoryRef"))
                || !Json.string(value, "tenantId", "").equals(input.get("tenantId"))
                || !Json.string(value, "sourceLanguage", "").equals(input.get("sourceLanguage"))
                || !Json.string(value, "targetLanguage", "").equals(input.get("targetLanguage"))
                || !Json.string(value, "certificationStatus", "").equals("NOT_CERTIFIED")) {
            throw new IOException("TRANSLATION_RESULT_SUBJECT_INVALID");
        }
        String status = Json.string(value, "status", "");
        if (!java.util.Set.of("COMPLETE", "PARTIAL", "BLOCKED").contains(status)) {
            throw new IOException("TRANSLATION_RESULT_STATUS_INVALID");
        }
        return status;
    }
    private static long integer(Object value) {
        return value instanceof Number number && Double.isFinite(number.doubleValue())
                && number.doubleValue() == number.longValue() ? number.longValue() : -1;
    }
}
