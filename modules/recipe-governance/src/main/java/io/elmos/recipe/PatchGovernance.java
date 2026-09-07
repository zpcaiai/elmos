package io.elmos.recipe;

import io.elmos.recipe.RecipeModels.*;

import java.util.*;

public final class PatchGovernance {
    private static final Set<String> SENSITIVE_INTENTS = Set.of("SECURITY_CONFIGURATION", "DATABASE_SCHEMA",
            "PUBLIC_API", "SERIALIZATION", "TRANSACTION", "PRODUCTION_DEPLOYMENT");

    public List<PatchSegment> segment(String migrationStepId, String patchArtifactPrefix,
                                      List<FileResult> changes, PatchPolicy policy) {
        Map<Key,List<FileResult>> groups = new TreeMap<>(Comparator.comparing(Key::intent).thenComparing(Key::module));
        for (FileResult change : changes) {
            if (change.binary()) groups.computeIfAbsent(new Key("BINARY", change.module()), ignored -> new ArrayList<>()).add(change);
            else groups.computeIfAbsent(new Key(normalizeIntent(change.semanticIntent()), change.module()), ignored -> new ArrayList<>()).add(change);
        }
        List<PatchSegment> result = new ArrayList<>(); int sequence = 1;
        for (Map.Entry<Key,List<FileResult>> entry : groups.entrySet()) {
            List<FileResult> pending = new ArrayList<>(entry.getValue()); pending.sort(Comparator.comparing(FileResult::afterPath));
            while (!pending.isEmpty()) {
                List<FileResult> current = new ArrayList<>(); int lines = 0;
                while (!pending.isEmpty() && current.size() < policy.maximumFilesPerSegment()) {
                    FileResult next = pending.getFirst();
                    if (!current.isEmpty() && lines + next.changedLines() > policy.maximumChangedLinesPerSegment()) break;
                    current.add(pending.removeFirst()); lines += next.changedLines();
                }
                if (current.isEmpty()) current.add(pending.removeFirst());
                List<String> findings = new ArrayList<>();
                boolean outside = current.stream().anyMatch(change -> policy.allowedPathPrefixes().stream().noneMatch(change.afterPath()::startsWith));
                boolean deleted = current.stream().anyMatch(FileResult::deleted), binary = current.stream().anyMatch(FileResult::binary);
                if (outside) findings.add("PATCH_OUTSIDE_STEP_SCOPE"); if (deleted) findings.add("PATCH_UNEXPECTED_FILE_DELETE");
                if (binary) findings.add("PATCH_BINARY_FILE_CHANGED");
                if (current.size() >= policy.maximumFilesPerSegment() || current.stream().mapToInt(FileResult::changedLines).sum() > policy.maximumChangedLinesPerSegment())
                    findings.add("PATCH_TOO_LARGE");
                Risk risk = current.stream().map(FileResult::risk).max(Comparator.comparingInt(Enum::ordinal)).orElse(Risk.LOW);
                boolean manual = risk.ordinal() >= Risk.HIGH.ordinal() || SENSITIVE_INTENTS.contains(entry.getKey().intent())
                        || policy.manualReviewIntents().contains(entry.getKey().intent()) || !findings.isEmpty();
                String segmentId = "segment-" + String.format("%03d", sequence++);
                result.add(new PatchSegment("1.0", segmentId, migrationStepId, entry.getKey().intent(),
                        current.stream().map(FileResult::actualRecipe).distinct().sorted().toList(),
                        current.stream().map(FileResult::module).distinct().sorted().toList(),
                        current.stream().map(FileResult::afterPath).sorted().toList(), risk,
                        validations(entry.getKey().intent()), manual, patchArtifactPrefix + "/" + segmentId + ".diff", findings));
            }
        }
        return List.copyOf(result);
    }

    private static String normalizeIntent(String intent) {
        String value = intent.toUpperCase(Locale.ROOT);
        return value.contains("FORMAT") ? "FORMATTING_ONLY" : value;
    }
    private static List<String> validations(String intent) {
        if (intent.contains("SECURITY")) return List.of("compile", "security-contract-tests", "authorization-review");
        if (intent.contains("DATABASE") || intent.contains("TRANSACTION")) return List.of("compile", "database-schema-diff", "transaction-tests");
        if (intent.contains("PUBLIC_API")) return List.of("compile", "api-compatibility");
        if (intent.equals("FORMATTING_ONLY")) return List.of("formatting-diff-only");
        return List.of("compile", "targeted-tests");
    }
    private record Key(String intent, String module) {}
}
