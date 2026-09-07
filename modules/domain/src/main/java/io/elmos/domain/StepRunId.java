package io.elmos.domain;
public record StepRunId(String value) { public StepRunId { value = Identifiers.require(value, "stepRunId"); } public static StepRunId random() { return new StepRunId(Identifiers.random()); } }

