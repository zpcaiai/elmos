package io.elmos.repair;

import io.elmos.repair.RepairModels.*;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class FailureNormalizer {
    private static final Pattern SECRET = Pattern.compile("(?i)(authorization|token|password|secret|api[-_]?key)\\s*[:=]\\s*[^\\s,;]+", Pattern.MULTILINE);
    private static final Pattern ABSOLUTE_PATH = Pattern.compile("(?:/Users|/home|/workspace|[A-Z]:\\\\)[^\\s:]+", Pattern.CASE_INSENSITIVE);
    private static final Pattern LINE_NUMBER = Pattern.compile("(?::|\\[)(\\d+)(?::\\d+)?(?:\\])?");
    private static final Pattern SYMBOL = Pattern.compile("(?i)(?:symbol:|cannot find symbol\\s*(?:class|method)?)\\s*([A-Za-z_$][A-Za-z0-9_$.<>]*)");

    public Failure normalize(RawFailure raw) {
        String sanitized = sanitize(raw.log());
        ErrorCategory category = classify(sanitized, raw.stage());
        String symbol = extractSymbol(sanitized);
        String canonical = canonicalize(sanitized);
        String fingerprint = hash(raw.stage() + "\n" + category + "\n" + raw.module() + "\n" + symbol + "\n" + canonical);
        return new Failure("failure-" + fingerprint.substring(0, 24), raw.stage(), category, raw.module(), symbol,
                truncate(canonical, 2000), fingerprint, List.of("log://" + raw.source()), retryable(category));
    }

    public List<FailureCluster> cluster(List<Failure> failures) {
        Map<String,List<Failure>> grouped = new TreeMap<>();
        for (Failure failure : failures) grouped.computeIfAbsent(failure.fingerprint(), ignored -> new ArrayList<>()).add(failure);
        List<FailureCluster> result = new ArrayList<>();
        for (Map.Entry<String,List<Failure>> entry : grouped.entrySet()) {
            List<Failure> members = entry.getValue().stream().sorted(Comparator.comparing(Failure::failureId)).toList();
            Failure primary = members.getFirst();
            result.add(new FailureCluster("cluster-" + entry.getKey().substring(0, 24), entry.getKey(), primary.failureId(),
                    members.stream().map(Failure::failureId).toList(), primary.category(), primary.stage(), primary.module()));
        }
        return List.copyOf(result);
    }

    public static String sanitize(String value) {
        String result = SECRET.matcher(value).replaceAll("$1=[REDACTED]");
        result = ABSOLUTE_PATH.matcher(result).replaceAll("<WORKSPACE_PATH>");
        return result.replaceAll("(?i)(session|request|trace)[-_ ]?id[:= ]+[a-z0-9-]+", "$1-id=<ID>")
                .replaceAll("\\b20\\d{2}-\\d{2}-\\d{2}[T ][0-9:.+-]+Z?\\b", "<TIMESTAMP>");
    }

    private static ErrorCategory classify(String value, Stage stage) {
        String lower = value.toLowerCase(Locale.ROOT);
        if (lower.contains("could not resolve") || lower.contains("dependency resolution")) return ErrorCategory.DEPENDENCY;
        if (lower.contains("cannot find symbol")) return ErrorCategory.MISSING_SYMBOL;
        if (lower.contains("incompatible types") || lower.contains("cannot be converted")) return ErrorCategory.TYPE_MISMATCH;
        if (lower.contains("assertionerror") || lower.contains("tests run:") && lower.contains("failures:")) return ErrorCategory.TEST_FAILURE;
        if (lower.contains("testcontainers") || lower.contains("docker environment")) return ErrorCategory.TEST_INFRASTRUCTURE;
        if (lower.contains("outofmemory") || lower.contains("resource exhausted")) return ErrorCategory.RESOURCE;
        if (lower.contains("timed out") || lower.contains("timeout")) return ErrorCategory.TIMEOUT;
        if (lower.contains("permission denied") || lower.contains("forbidden")) return ErrorCategory.SECURITY;
        if (stage == Stage.COMPILE) return ErrorCategory.COMPILATION;
        return ErrorCategory.UNKNOWN;
    }

    private static String extractSymbol(String value) {
        Matcher matcher = SYMBOL.matcher(value);
        return matcher.find() ? matcher.group(1) : "<none>";
    }

    private static String canonicalize(String value) {
        return LINE_NUMBER.matcher(value).replaceAll(":<LINE>").replaceAll("\\s+", " ").trim().toLowerCase(Locale.ROOT);
    }

    private static boolean retryable(ErrorCategory category) {
        return category != ErrorCategory.SECURITY && category != ErrorCategory.UNKNOWN;
    }
    private static String truncate(String value, int max) { return value.length() <= max ? value : value.substring(0, max); }
    static String hash(String value) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8))); }
        catch (Exception error) { throw new IllegalStateException(error); }
    }
}
