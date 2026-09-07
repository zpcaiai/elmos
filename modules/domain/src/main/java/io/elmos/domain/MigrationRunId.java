package io.elmos.domain;
public record MigrationRunId(String value) { public MigrationRunId { value = Identifiers.require(value, "migrationRunId"); } public static MigrationRunId random() { return new MigrationRunId(Identifiers.random()); } }

