package io.elmos.domain;
public record EvidenceId(String value) { public EvidenceId { value = Identifiers.require(value, "evidenceId"); } public static EvidenceId random() { return new EvidenceId(Identifiers.random()); } }

