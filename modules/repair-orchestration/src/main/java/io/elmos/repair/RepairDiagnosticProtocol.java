package io.elmos.repair;

import io.elmos.repair.RepairLoopModels.*;

import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Normalizes diagnostics without erasing native codes, redacted messages or raw evidence references. */
public final class RepairDiagnosticProtocol {
    private static final Pattern SECRET = Pattern.compile(
            "(?i)(authorization|token|password|secret|api[-_]?key)\\s*[:=]\\s*[^\\s,;]+", Pattern.MULTILINE);
    private static final Pattern ABSOLUTE_PATH = Pattern.compile(
            "(?:/Users|/home|/workspace|[A-Z]:\\\\)[^\\s:]+", Pattern.CASE_INSENSITIVE);
    private static final Pattern LINE = Pattern.compile("(?::|\\[)(\\d+)(?::\\d+)?(?:\\])?");
    private static final Pattern SYMBOL = Pattern.compile(
            "(?i)(?:symbol:|cannot find symbol\\s*(?:class|method)?|name|type)\\s*['\"]?([A-Za-z_$][A-Za-z0-9_$.<>]*)");

    public List<Diagnostic> normalize(String repairRunId, List<RawDiagnostic> rawValues) {
        List<Diagnostic> values = new ArrayList<>();
        for (RawDiagnostic raw : rawValues) values.add(normalize(repairRunId, raw));
        return values.stream().sorted(Comparator.comparing(Diagnostic::diagnosticId)).toList();
    }

    public Diagnostic normalize(String repairRunId, RawDiagnostic raw) {
        String message = sanitize(raw.message());
        DiagnosticCategory category = classify(raw, message);
        Severity severity = severity(raw, category);
        String symbol = normalizeSymbol(raw.symbol(), message);
        String signature = canonical(message);
        String fingerprint = RepairLoopIds.hash(List.of(raw.phase(), nullToEmpty(raw.nativeCode()), category,
                raw.moduleId(), symbol, nullToEmpty(raw.dependency()), nullToEmpty(raw.targetDeclarationId()), signature));
        double confidence = raw.categoryHint() == null || raw.categoryHint().isBlank()
                ? category == DiagnosticCategory.UNKNOWN ? 0.35 : 0.82 : 0.97;
        return new Diagnostic(RepairLoopIds.id("diag", repairRunId, fingerprint), repairRunId,
                raw.phase(), raw.tool(), raw.nativeCode(), category, severity, message, raw.moduleId(),
                normalizePath(raw.file()), raw.line(), raw.column(), symbol, raw.dependency(),
                raw.targetDeclarationId(), raw.sourceTestId(), raw.rawOutputRef(), fingerprint, confidence);
    }

    public List<DiagnosticCluster> cluster(List<Diagnostic> diagnostics) {
        Map<String,List<Diagnostic>> groups = new TreeMap<>();
        for (Diagnostic diagnostic : diagnostics) {
            String discriminator = !"<none>".equals(diagnostic.normalizedSymbol()) ? diagnostic.normalizedSymbol()
                    : diagnostic.dependency() != null ? diagnostic.dependency()
                    : diagnostic.sourceTestId() != null ? diagnostic.sourceTestId()
                    : diagnostic.fingerprint();
            String key = RepairLoopIds.hash(List.of(diagnostic.moduleId(), diagnostic.category(),
                    nullToEmpty(diagnostic.nativeCode()), discriminator));
            groups.computeIfAbsent(key, ignored -> new ArrayList<>()).add(diagnostic);
        }
        List<DiagnosticCluster> result = new ArrayList<>();
        for (Map.Entry<String,List<Diagnostic>> entry : groups.entrySet()) {
            List<Diagnostic> members = entry.getValue().stream()
                    .sorted(Comparator.comparing(Diagnostic::diagnosticId)).toList();
            Diagnostic first = members.getFirst();
            Severity maximum = members.stream().map(Diagnostic::severity)
                    .max(Comparator.comparingInt(Enum::ordinal)).orElse(Severity.ERROR);
            List<String> roots = members.stream()
                    .flatMap(value -> java.util.stream.Stream.of(
                            value.normalizedSymbol(), value.dependency(), value.targetDeclarationId()))
                    .filter(value -> value != null && !value.isBlank() && !"<none>".equals(value)).distinct().sorted().toList();
            double confidence = members.stream().mapToDouble(Diagnostic::confidence).average().orElse(0.5);
            result.add(new DiagnosticCluster("cluster:" + entry.getKey(), first.category(),
                    members.stream().map(Diagnostic::diagnosticId).toList(), roots,
                    members.stream().map(Diagnostic::moduleId).distinct().sorted().toList(),
                    causalChain(first.category()), confidence, fixScope(first.category()), priority(maximum, first.category()), maximum));
        }
        return List.copyOf(result);
    }

    public List<AttributionRecord> attribute(List<DiagnosticCluster> clusters, List<Diagnostic> diagnostics,
                                             SourceBaseline baseline) {
        Map<String,Diagnostic> byId = new HashMap<>();
        diagnostics.forEach(value -> byId.put(value.diagnosticId(), value));
        List<AttributionRecord> result = new ArrayList<>();
        for (DiagnosticCluster cluster : clusters) {
            List<Diagnostic> members = cluster.diagnosticIds().stream().map(byId::get).filter(Objects::nonNull).toList();
            long sourceMatches = members.stream().filter(value -> baseline.diagnosticFingerprints().contains(value.fingerprint())).count();
            Attribution attribution;
            List<String> evidence = new ArrayList<>();
            double confidence;
            if (sourceMatches > 0 && sourceMatches < members.size()) {
                attribution = Attribution.MIXED; confidence = 0.88; evidence.add("source-and-target-diagnostic-members");
            } else if (!members.isEmpty() && sourceMatches == members.size()) {
                attribution = Attribution.SOURCE_EXISTING; confidence = 0.98; evidence.add("source-baseline-fingerprint-match");
            } else if (cluster.primaryCategory() == DiagnosticCategory.ENVIRONMENT) {
                attribution = Attribution.TARGET_ENVIRONMENT; confidence = 0.94; evidence.add("environment-category");
            } else if (cluster.primaryCategory() == DiagnosticCategory.DEPENDENCY
                    && members.stream().anyMatch(value -> containsAny(value.message(), "registry", "network", "unavailable", "timeout"))) {
                attribution = Attribution.DEPENDENCY_INFRASTRUCTURE; confidence = 0.82; evidence.add("dependency-infrastructure-signal");
            } else if (cluster.primaryCategory() == DiagnosticCategory.FLAKY) {
                attribution = Attribution.TEST_FLAKY; confidence = 0.95; evidence.add("non-deterministic-test-signal");
            } else if (isTest(cluster.primaryCategory()) && hasSourceStatus(members, baseline, TestStatus.PASSED)) {
                attribution = Attribution.TEST_MIGRATION; confidence = 0.9; evidence.add("corresponding-source-test-passed");
            } else if (cluster.primaryCategory() == DiagnosticCategory.UNKNOWN || !baseline.comparable()) {
                attribution = Attribution.UNKNOWN; confidence = baseline.comparable() ? 0.35 : 0.1;
                evidence.add(baseline.comparable() ? "insufficient-attribution-evidence" : "source-target-baseline-not-comparable");
            } else {
                attribution = Attribution.MIGRATION_INTRODUCED; confidence = 0.78;
                evidence.add("absent-from-comparable-source-baseline");
            }
            result.add(new AttributionRecord(cluster.clusterId(), attribution, evidence, confidence));
        }
        return List.copyOf(result);
    }

    static String sanitize(String value) {
        String sanitized = SECRET.matcher(value).replaceAll("$1=[REDACTED]");
        return ABSOLUTE_PATH.matcher(sanitized).replaceAll("<WORKSPACE_PATH>")
                .replaceAll("(?i)(session|request|trace)[-_ ]?id[:= ]+[a-z0-9-]+", "$1-id=<ID>")
                .replaceAll("\\b20\\d{2}-\\d{2}-\\d{2}[T ][0-9:.+-]+Z?\\b", "<TIMESTAMP>");
    }

    private static DiagnosticCategory classify(RawDiagnostic raw, String message) {
        String hint = raw.categoryHint() == null ? "" : raw.categoryHint().trim().replace('-', '_').toUpperCase(Locale.ROOT);
        try { if (!hint.isEmpty()) return DiagnosticCategory.valueOf(hint); }
        catch (IllegalArgumentException ignored) { /* retain unknown hint in native evidence */ }
        String code = nullToEmpty(raw.nativeCode()).toUpperCase(Locale.ROOT);
        String lower = message.toLowerCase(Locale.ROOT);
        if (Set.of("CS0246", "TS2304", "TS2307").contains(code) || containsAny(lower, "cannot find symbol", "nameerror", "unknown import"))
            return DiagnosticCategory.SYMBOL;
        if (code.startsWith("SEC") || containsAny(lower, "sql injection", "path traversal", "authorization gap", "weak crypt"))
            return DiagnosticCategory.SECURITY;
        if (containsAny(lower, "could not resolve", "package not found", "version conflict", "lockfile"))
            return DiagnosticCategory.DEPENDENCY;
        if (containsAny(lower, "incompatible types", "cannot be converted", "not assignable", "type mismatch"))
            return DiagnosticCategory.TYPE;
        if (containsAny(lower, "null dereference", "possibly null", "none is not")) return DiagnosticCategory.NULLABILITY;
        if (containsAny(lower, "fixture", "mock", "stub")) return DiagnosticCategory.TEST_FIXTURE;
        if (containsAny(lower, "assertionerror", "expected:", "assertion failed")) return DiagnosticCategory.TEST_ASSERTION;
        if (containsAny(lower, "no tests found", "0 tests", "test discovery")) return DiagnosticCategory.TEST_DISCOVERY;
        if (containsAny(lower, "flaky", "order-dependent", "non-deterministic")) return DiagnosticCategory.FLAKY;
        if (containsAny(lower, "permission denied", "docker environment", "sandbox unavailable", "resource exhausted"))
            return DiagnosticCategory.ENVIRONMENT;
        if (raw.phase() == Phase.COMPILE) return DiagnosticCategory.SYNTAX;
        if (raw.phase() == Phase.STATIC_ANALYSIS) return DiagnosticCategory.STATIC_ANALYSIS;
        if (raw.phase() == Phase.TEST_DISCOVERY) return DiagnosticCategory.TEST_DISCOVERY;
        if (raw.phase() == Phase.RESTORE) return DiagnosticCategory.DEPENDENCY;
        return DiagnosticCategory.UNKNOWN;
    }

    private static Severity severity(RawDiagnostic raw, DiagnosticCategory category) {
        String hint = raw.severityHint() == null ? "" : raw.severityHint().trim().toUpperCase(Locale.ROOT);
        try { if (!hint.isEmpty()) return Severity.valueOf(hint); }
        catch (IllegalArgumentException ignored) { /* infer below */ }
        if (category == DiagnosticCategory.SECURITY) return Severity.CRITICAL;
        if (Set.of(DiagnosticCategory.ENVIRONMENT, DiagnosticCategory.DEPENDENCY,
                DiagnosticCategory.BUILD_CONFIGURATION, DiagnosticCategory.TEST_DISCOVERY).contains(category))
            return Severity.BLOCKING;
        return Severity.ERROR;
    }

    private static String normalizeSymbol(String explicit, String message) {
        if (explicit != null && !explicit.isBlank()) return explicit.trim().replaceAll("\\s+", "");
        Matcher matcher = SYMBOL.matcher(message);
        return matcher.find() ? matcher.group(1) : "<none>";
    }

    private static String normalizePath(String value) {
        if (value == null || value.isBlank()) return null;
        return ABSOLUTE_PATH.matcher(value.replace('\\', '/')).replaceAll("<WORKSPACE_PATH>");
    }

    private static String canonical(String value) {
        return LINE.matcher(value).replaceAll(":<LINE>").replaceAll("\\s+", " ")
                .trim().toLowerCase(Locale.ROOT);
    }

    private static boolean hasSourceStatus(List<Diagnostic> diagnostics, SourceBaseline baseline, TestStatus status) {
        return diagnostics.stream().map(Diagnostic::sourceTestId).filter(Objects::nonNull)
                .map(baseline.sourceTests()::get).anyMatch(status::equals);
    }
    private static boolean isTest(DiagnosticCategory category) {
        return Set.of(DiagnosticCategory.TEST_ASSERTION, DiagnosticCategory.TEST_COMPILATION,
                DiagnosticCategory.TEST_DISCOVERY, DiagnosticCategory.TEST_FIXTURE).contains(category);
    }
    private static List<String> causalChain(DiagnosticCategory category) {
        return switch (category) {
            case DEPENDENCY -> List.of("dependency-resolution", "symbol-resolution", "downstream-compilation");
            case SYMBOL -> List.of("symbol-binding", "type-checking", "downstream-compilation");
            case TEST_FIXTURE -> List.of("fixture-setup", "test-execution", "assertion");
            default -> List.of(category.name().toLowerCase(Locale.ROOT));
        };
    }
    private static String fixScope(DiagnosticCategory category) {
        return switch (category) {
            case DEPENDENCY, BUILD_CONFIGURATION -> "build-file";
            case TEST_DISCOVERY, TEST_FIXTURE, TEST_ASSERTION -> "test";
            case ENVIRONMENT -> "environment";
            default -> "declaration";
        };
    }
    private static String priority(Severity severity, DiagnosticCategory category) {
        if (severity == Severity.CRITICAL || category == DiagnosticCategory.SECURITY) return "P0";
        if (severity == Severity.BLOCKING || Set.of(DiagnosticCategory.DEPENDENCY,
                DiagnosticCategory.BUILD_CONFIGURATION, DiagnosticCategory.TEST_DISCOVERY).contains(category)) return "P1";
        if (severity == Severity.ERROR) return "P2";
        if (severity == Severity.WARNING) return "P3";
        return "P4";
    }
    private static boolean containsAny(String value, String... needles) {
        String lower = value.toLowerCase(Locale.ROOT);
        return Arrays.stream(needles).anyMatch(lower::contains);
    }
    private static String nullToEmpty(String value) { return value == null ? "" : value; }
}
