package com.acme.migration.engine.api;

import java.time.Instant;
import java.util.List;

public record PspDocument(
        String schemaVersion,
        String language,
        Instant generatedAt,
        String repository,
        int sourceFileCount,
        List<String> packages,
        List<SourceUnit> sourceUnits) {

    public record SourceUnit(String path, String packageName, List<String> declaredTypes) {}
}
