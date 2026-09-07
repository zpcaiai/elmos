package io.elmos.domain;
public record MigrationPlanId(String value) { public MigrationPlanId { value = Identifiers.require(value, "migrationPlanId"); } public static MigrationPlanId random() { return new MigrationPlanId(Identifiers.random()); } }

